"""Slice 6 of the Session Reorg plan
(`~/.claude/plans/sparkling-triaging-otter.md`) — analyze a source
session and propose how its messages should be split into coherent
sub-sessions. Read-only: nothing in here writes to the database; the
caller (route handler) takes the proposals back to the frontend, the
user approves per-card, and `/reorg/split` does the actual moves.

Two analyzers behind one entrypoint:

- **Heuristic.** Deterministic, no LLM. Splits on long quiet gaps
  (>2h) and within each segment splits on Jaccard topic distance
  >0.7 across a 3-message sliding window of user-turn prompts.
  Always available, always cheap.

- **LLM.** One-shot `claude_agent_sdk.query(...)` call gated on
  `agent.enable_llm_reorg_analyze=True`. Reads a numbered message
  digest, returns strict JSON with `proposals[].topic / rationale /
  message_ids`. Falls back to heuristic on disabled config or two
  consecutive parse failures.

The module name is `_reorg_analyze` (sibling to `_reorg`) so the
existing store re-export pattern stays — `bearings.db.store` doesn't
need to grow new symbols (the route imports directly from this
module to keep the public DB surface small).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

logger = logging.getLogger(__name__)

# Time gap (seconds) above which we always start a new heuristic
# segment. Two hours is the empirical "I came back the next day"
# threshold from the Checklists session that motivated this plan —
# inside two hours, gaps usually mean a model run or context-think;
# beyond, the user has gone away and is starting something new.
TIME_GAP_SECONDS = 2 * 60 * 60

# Jaccard distance above which two adjacent windows are considered
# topical-shifts. Empirically Jaccard distance for the same-topic
# windows lands around 0.3-0.5 on noisy real prompts; >0.7 is the
# clear "different topic" cliff.
TOPIC_DISTANCE_THRESHOLD = 0.7

# Sliding window size for topic shift detection. Three keeps the
# comparison robust to a single off-topic side-question without
# overfitting (a single odd message won't tip the window).
TOPIC_WINDOW = 3

# Stop-words removed before tokenization for Jaccard. Hand-rolled
# rather than pulled from nltk — keeps the deps surface tight and
# the list short enough to read at a glance.
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "have",
        "has",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "should",
        "so",
        "the",
        "their",
        "them",
        "then",
        "this",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yes",
        "no",
        "ok",
        "okay",
        "we",
        "us",
        "that",
        "now",
        "also",
        "just",
        "than",
        "too",
    }
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")


def _tokenize(text: str) -> set[str]:
    """Lower-case the text, strip stop-words, return the unique-token
    set used for Jaccard scoring. Only words ≥3 chars survive — drops
    "a"/"is"/"of" without a stop-list lookup, and the dash/underscore
    allow keeps "session-id" and "tool_call" intact as single tokens
    (otherwise we'd Jaccard against the substrings and lose signal)."""
    return {w.lower() for w in _WORD_RE.findall(text or "") if w.lower() not in _STOP_WORDS}


def _jaccard_distance(a: set[str], b: set[str]) -> float:
    """Return 1 - |a∩b|/|a∪b|. Empty-vs-empty returns 0 (identical
    nothings); empty-vs-nonempty returns 1 (maximally different)."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return 1.0 - (len(a & b) / len(union))


def _parse_iso(stamp: str | None) -> datetime | None:
    """`messages.created_at` is an ISO timestamp written by `_now()`
    — `datetime.fromisoformat` reads it round-trip. Returns None on
    parse failure so the caller treats the gap as zero."""
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None


@dataclass(frozen=True)
class _Segment:
    """Internal scratch shape used only inside this module.

    `start_idx` / `end_idx` index into the input messages list so the
    final proposal can re-snip the slice in source order without
    re-walking the whole list. `reason` is the deterministic split
    label the heuristic emits as the proposal's rationale."""

    start_idx: int
    end_idx: int  # exclusive
    reason: str


def _segment_by_time_gap(messages: Sequence[dict[str, Any]]) -> list[_Segment]:
    """First-pass split: any adjacent pair more than `TIME_GAP_SECONDS`
    apart starts a new segment. Returns at least one segment when the
    input is non-empty.

    Both segments adjacent to a time-gap boundary carry "time gap" in
    their `reason` so the confidence-scoring path in `heuristic_analyze`
    treats them symmetrically — splitting at a real day-break boundary
    is high-confidence on both sides, not just the leading one."""
    if not messages:
        return []
    breaks: list[tuple[int, int]] = []  # (index, gap minutes)
    for i in range(1, len(messages)):
        prev_ts = _parse_iso(messages[i - 1].get("created_at"))
        curr_ts = _parse_iso(messages[i].get("created_at"))
        if prev_ts is None or curr_ts is None:
            continue
        gap = (curr_ts - prev_ts).total_seconds()
        if gap > TIME_GAP_SECONDS:
            breaks.append((i, int(gap // 60)))
    if not breaks:
        return [_Segment(start_idx=0, end_idx=len(messages), reason="initial segment")]

    segments: list[_Segment] = []
    start = 0
    for break_i, mins in breaks:
        segments.append(
            _Segment(
                start_idx=start,
                end_idx=break_i,
                reason=f"split on time gap ({mins} min)",
            )
        )
        start = break_i
    last_mins = breaks[-1][1]
    segments.append(
        _Segment(
            start_idx=start,
            end_idx=len(messages),
            reason=f"after time gap ({last_mins} min)",
        )
    )
    return segments


def _segment_by_topic_shift(
    messages: Sequence[dict[str, Any]],
    seg: _Segment,
) -> list[_Segment]:
    """Within a single time-gap segment, slide a `TOPIC_WINDOW`-sized
    window of user-turn token sets and split when the previous-window
    vs next-window Jaccard distance exceeds the threshold. Assistant
    turns are skipped for tokenization (their content is generated
    text, not a topic anchor); they ride along with the surrounding
    user turns."""
    user_indices = [
        i for i in range(seg.start_idx, seg.end_idx) if messages[i].get("role") == "user"
    ]
    if len(user_indices) < TOPIC_WINDOW * 2:
        # Not enough user turns to slide a meaningful window — keep
        # the segment whole.
        return [seg]

    token_sets = [_tokenize(str(messages[i].get("content", ""))) for i in user_indices]
    splits: list[int] = []  # indices into messages where a new segment begins
    for w in range(TOPIC_WINDOW, len(token_sets) - TOPIC_WINDOW + 1):
        prev_window: set[str] = set().union(*token_sets[w - TOPIC_WINDOW : w])
        next_window: set[str] = set().union(*token_sets[w : w + TOPIC_WINDOW])
        if _jaccard_distance(prev_window, next_window) > TOPIC_DISTANCE_THRESHOLD:
            split_at = user_indices[w]
            # Avoid stacking splits within the same window — one shift
            # gets one segment break.
            if not splits or split_at - splits[-1] >= TOPIC_WINDOW:
                splits.append(split_at)

    if not splits:
        return [seg]
    out: list[_Segment] = []
    cursor = seg.start_idx
    for s in splits:
        out.append(
            _Segment(
                start_idx=cursor,
                end_idx=s,
                reason=f"topic shift at message {s - seg.start_idx + 1}",
            )
        )
        cursor = s
    out.append(
        _Segment(
            start_idx=cursor,
            end_idx=seg.end_idx,
            reason="trailing segment after topic shift",
        )
    )
    return out


def _segments_for(messages: Sequence[dict[str, Any]]) -> list[_Segment]:
    """Compose the two passes: time-gap first, topic-shift within
    each gap segment. Single-segment results are tolerated — the
    route turns "one segment covering all messages" into an empty
    proposal list (nothing to split)."""
    out: list[_Segment] = []
    for seg in _segment_by_time_gap(messages):
        out.extend(_segment_by_topic_shift(messages, seg))
    return out


def _segment_topic_label(messages: Sequence[dict[str, Any]], seg: _Segment) -> str:
    """Best-effort topic label for a heuristic proposal — the most
    common non-stop-word in the segment's user-turn prompts, or a
    generic "Segment N" when there's nothing to latch onto. Bounded
    to ≤40 chars so the UI doesn't have to truncate."""
    counts: dict[str, int] = {}
    for i in range(seg.start_idx, seg.end_idx):
        if messages[i].get("role") != "user":
            continue
        for token in _tokenize(str(messages[i].get("content", ""))):
            counts[token] = counts.get(token, 0) + 1
    if not counts:
        return ""
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    label = " ".join(t for t, _ in top)
    return label[:40]


def heuristic_analyze(
    messages: Sequence[dict[str, Any]],
    *,
    source_tag_ids: Sequence[int],
) -> list[dict[str, Any]]:
    """Deterministic analyzer. Returns a list of proposal dicts shaped
    like `ReorgProposal` — the route wraps them in the Pydantic model
    after merging suggested-session data.

    Empty result means "the heuristic doesn't think this needs to be
    split"; callers shouldn't treat it as an error."""
    segments = _segments_for(messages)
    # If only one segment (no gaps, no topic shifts), there's nothing
    # to propose — the source is already coherent by the heuristic's
    # lights.
    if len(segments) <= 1:
        return []

    proposals: list[dict[str, Any]] = []
    tag_list = list(source_tag_ids) or []
    for n, seg in enumerate(segments, start=1):
        msg_ids = [str(messages[i]["id"]) for i in range(seg.start_idx, seg.end_idx)]
        if not msg_ids:
            continue
        label = _segment_topic_label(messages, seg)
        topic = f"Segment {n}: {label}" if label else f"Segment {n}"
        title = f"Segment {n} ({len(msg_ids)} messages)"
        confidence = 1.0 if "time gap" in seg.reason else 0.6
        proposals.append(
            {
                "topic": topic,
                "rationale": seg.reason,
                "confidence": confidence,
                "message_ids": msg_ids,
                "suggested_session": {
                    "title": title,
                    "description": None,
                    "tag_ids": tag_list,
                },
            }
        )
    return proposals


# ---------------------------------------------------------------------
# LLM analyzer
# ---------------------------------------------------------------------

_LLM_SYSTEM_PROMPT = """You are a session-triage analyzer. You read a numbered list of
chat messages from a single Bearings session and decide whether the
session should be split into multiple coherent sub-sessions.

Output rules:
- Reply with ONE JSON object and nothing else (no prose, no markdown
  code fences). The schema is:
  {"proposals": [
     {"topic": "<short topic phrase>",
      "rationale": "<one sentence on why these messages belong together>",
      "confidence": <float 0..1>,
      "message_ids": ["<id>", ...],
      "title": "<suggested session title, max 60 chars>"}
  ]}
- Every `message_ids` value MUST be a real id from the input list.
- Each id appears in AT MOST one proposal (no overlaps).
- Order proposals so each proposal's message_ids are contiguous in
  the original session order.
- If the session is already coherent (one topic), return
  {"proposals": []}.
- Title may reuse `topic` when nothing better fits.
"""

_LLM_MAX_MESSAGES = 200
_LLM_MAX_CHARS_PER_MSG = 400


def _build_llm_user_prompt(messages: Sequence[dict[str, Any]]) -> str:
    """Render a message digest the LLM can scan in a single turn.

    Each line has the format `[id] role: content` truncated to
    `_LLM_MAX_CHARS_PER_MSG`. Up to `_LLM_MAX_MESSAGES` rows are
    included; oversized sessions are sampled (head + tail) so the
    analyzer still sees both ends of the conversation. The route
    enforces the cap before calling but we belt-and-brace here."""
    rows = list(messages)
    if len(rows) > _LLM_MAX_MESSAGES:
        head = rows[: _LLM_MAX_MESSAGES // 2]
        tail = rows[-_LLM_MAX_MESSAGES // 2 :]
        rows = head + tail
    lines: list[str] = []
    for r in rows:
        content = str(r.get("content", ""))
        if len(content) > _LLM_MAX_CHARS_PER_MSG:
            content = content[:_LLM_MAX_CHARS_PER_MSG] + "…"
        lines.append(f"[{r.get('id', '')}] {r.get('role', '?')}: {content}")
    return (
        "Analyze the following Bearings session messages and propose splits per the schema.\n\n"
        + "\n".join(lines)
    )


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """Pull the first balanced `{...}` block out of an LLM response and
    JSON-parse it. The model is instructed to emit raw JSON, but
    backticks / preface text creep in occasionally; the brace scan
    keeps the parser tolerant of that without trusting it."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                try:
                    parsed = json.loads(blob)
                    if isinstance(parsed, dict):
                        return parsed
                    return None
                except json.JSONDecodeError:
                    return None
    return None


def _validate_llm_proposals(
    parsed: dict[str, Any],
    valid_ids: set[str],
    source_tag_ids: Sequence[int],
) -> list[dict[str, Any]] | None:
    """Validate the model's structured response against the input
    message ids. Drops proposals that reference unknown ids or repeat
    an id seen earlier — first occurrence wins so the contiguous
    ordering in the prompt is preserved. Returns None when the shape
    is fundamentally wrong (no `proposals` key, etc.) so the caller
    can fall through to heuristic; returns [] for an explicit empty
    list (model thinks the session is coherent)."""
    raw = parsed.get("proposals")
    if not isinstance(raw, list):
        return None
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        ids_raw = entry.get("message_ids")
        if not isinstance(ids_raw, list):
            continue
        kept_ids: list[str] = []
        for mid in ids_raw:
            if not isinstance(mid, str):
                continue
            if mid not in valid_ids or mid in seen:
                continue
            kept_ids.append(mid)
            seen.add(mid)
        if not kept_ids:
            continue
        topic = str(entry.get("topic", "")).strip() or "Untitled segment"
        rationale = str(entry.get("rationale", "")).strip() or "LLM-suggested split"
        title = str(entry.get("title", "")).strip() or topic[:60]
        confidence_raw = entry.get("confidence", 0.7)
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = max(0.0, min(1.0, confidence))
        out.append(
            {
                "topic": topic[:80],
                "rationale": rationale[:200],
                "confidence": confidence,
                "message_ids": kept_ids,
                "suggested_session": {
                    "title": title[:60],
                    "description": None,
                    "tag_ids": list(source_tag_ids),
                },
            }
        )
    return out


# Type alias for the SDK callable so tests can monkeypatch a fake.
SDKQueryResult = Literal["ok", "parse_failed"]


async def _run_llm_query(
    messages: Sequence[dict[str, Any]],
    *,
    model: str,
    query_fn: Any | None = None,
) -> str:
    """Drive the SDK's one-shot `query()` call and concatenate its
    assistant text. Isolated so tests can monkeypatch `query_fn` with
    a fake async generator. The default branch imports the real SDK
    lazily to keep import cost off the hot path of routes that never
    enable LLM mode."""
    if query_fn is None:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            TextBlock,
            query,
        )

        options = ClaudeAgentOptions(
            model=model,
            system_prompt=_LLM_SYSTEM_PROMPT,
            permission_mode="default",
            max_turns=1,
            setting_sources=None,
        )
        prompt = _build_llm_user_prompt(messages)
        chunks: list[str] = []
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        chunks.append(block.text)
        return "".join(chunks)

    # Fake-injected path for tests. `query_fn` is an async function
    # returning the raw string the model would have produced.
    raw = await query_fn(messages)
    return str(raw)


async def llm_analyze(
    messages: Sequence[dict[str, Any]],
    *,
    source_tag_ids: Sequence[int],
    model: str,
    query_fn: Any | None = None,
) -> tuple[list[dict[str, Any]] | None, str]:
    """One-shot LLM analyzer. Returns (proposals, notes).

    `proposals` is None when the LLM call failed in a way the caller
    should surface as a heuristic fallback (parse error, empty
    response). An empty list is a valid "model says no split needed"
    answer and should NOT trigger fallback. `notes` is a short string
    describing what happened — empty on the happy path, populated on
    fallback / partial degrade.

    `query_fn` is the test seam: a coroutine that takes the messages
    and returns the raw response text. Pass None in production to
    use the real SDK."""
    valid_ids = {str(m["id"]) for m in messages}
    last_error = ""
    for attempt in range(2):
        try:
            text = await _run_llm_query(messages, model=model, query_fn=query_fn)
        except Exception as exc:  # noqa: BLE001
            last_error = f"LLM call failed: {exc!r}"
            logger.warning("LLM analyze attempt %d failed: %r", attempt + 1, exc)
            continue
        parsed = _extract_json_block(text)
        if parsed is None:
            last_error = "LLM returned unparseable JSON"
            logger.warning("LLM analyze attempt %d: unparseable JSON", attempt + 1)
            continue
        validated = _validate_llm_proposals(parsed, valid_ids, source_tag_ids)
        if validated is None:
            last_error = "LLM JSON missing 'proposals' list"
            logger.warning("LLM analyze attempt %d: shape mismatch", attempt + 1)
            continue
        return validated, ""
    return None, last_error or "LLM analyze failed"
