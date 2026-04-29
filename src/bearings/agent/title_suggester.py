"""Auto-suggest session titles plan (`~/.claude/plans/auto-suggesting-titles.md`).

One-shot LLM caller that proposes three candidate titles for an
existing Bearings session based on its recent messages. Mirrors
`bearings.db._reorg_analyze.llm_analyze` 1:1 — same SDK, same
two-attempt retry, same JSON-block extraction, same `query_fn` test
seam — so the patterns the codebase already validates carry over
without surprise.

The route handler in `bearings.api.routes_suggest_title` enforces the
config gate (`agent.enable_llm_title_suggest`) and the session-kind
check; this module is pure helper and assumes the caller has already
cleared those gates.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

# Up to this many messages from the session are rendered into the
# prompt. 200 matches the reorg-analyze cap — empirically enough
# context for the model to identify a coherent topic without blowing
# past Haiku's input budget. Sessions longer than this are sampled
# head + tail.
_MAX_MESSAGES = 200

# Per-message character cap. Long Bash outputs and tool-call dumps
# would otherwise dominate the digest and crowd out the user's actual
# prompts. 400 chars ≈ 100 tokens leaves room for ~200 messages
# while still fitting comfortably in a single Haiku turn.
_MAX_CHARS_PER_MSG = 400

# Hard cap on suggested-title length surfaced to the UI. Mirrors the
# v0.20.6 60-char limit on user-supplied titles in `NewSessionForm` so
# whatever the model emits fits the same field constraints.
_MAX_TITLE_CHARS = 60

# How many candidates we ask the model to produce. Three is the
# sweet spot — one usually too narrow, one usually too wide, one
# usually right. Same Haiku call cost as one candidate.
_NUM_CANDIDATES = 3

_SYSTEM_PROMPT = """You are a session-title summarizer. You read a numbered list of
chat messages from a single Bearings session and propose three
candidate titles that describe what the conversation is actually
about.

Output rules:
- Reply with ONE JSON object and nothing else (no prose, no markdown
  code fences). The schema is:
  {"titles": ["<title 1>", "<title 2>", "<title 3>"]}
- Exactly three titles.
- Each title is at most 60 characters.
- The three titles should reflect different abstraction levels:
  one narrow (specific feature/file/decision in play), one medium
  (the work item the session is delivering), one wide (the broad
  topic). Order: narrow, medium, wide.
- Title case or sentence case, no surrounding quotes, no trailing
  punctuation.
- If the session is too short or empty to summarize, still return
  three plausible titles based on whatever signal exists; never
  return fewer than three or an empty list.
"""


def _build_user_prompt(messages: Sequence[dict[str, Any]]) -> str:
    """Render a message digest for the model. Each line has the format
    `[id] role: content` truncated to `_MAX_CHARS_PER_MSG`. Up to
    `_MAX_MESSAGES` rows are included; oversized sessions are sampled
    head + tail so the model still sees both ends of the conversation.
    """
    rows = list(messages)
    if len(rows) > _MAX_MESSAGES:
        head = rows[: _MAX_MESSAGES // 2]
        tail = rows[-_MAX_MESSAGES // 2 :]
        rows = head + tail
    lines: list[str] = []
    for r in rows:
        content = str(r.get("content", ""))
        if len(content) > _MAX_CHARS_PER_MSG:
            content = content[:_MAX_CHARS_PER_MSG] + "…"
        lines.append(f"[{r.get('id', '')}] {r.get('role', '?')}: {content}")
    return (
        "Propose three candidate titles for the following Bearings "
        "session per the schema.\n\n" + "\n".join(lines)
    )


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """Pull the first balanced `{...}` block out of an LLM response and
    JSON-parse it. The model is instructed to emit raw JSON, but
    backticks / preface text creep in occasionally; the brace scan
    keeps the parser tolerant of that without trusting it. Mirrors
    `_reorg_analyze._extract_json_block`."""
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


_WHITESPACE_RE = re.compile(r"\s+")


def _clean_title(raw: Any) -> str | None:
    """Normalize a model-emitted title. Returns None if the value
    isn't a non-empty string after cleanup; otherwise returns the
    string trimmed, surrounding quotes stripped, internal whitespace
    collapsed, and clamped to `_MAX_TITLE_CHARS`."""
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    # Strip a single layer of surrounding quote characters in case the
    # model wrapped the title despite the system-prompt instruction.
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1].strip()
    s = _WHITESPACE_RE.sub(" ", s)
    if not s:
        return None
    return s[:_MAX_TITLE_CHARS]


def _validate_titles(parsed: dict[str, Any]) -> list[str] | None:
    """Validate the model's response shape. Returns the cleaned list
    on success (always exactly three entries), or None when the shape
    is fundamentally wrong (no `titles` key, not a list, fewer than
    three usable strings)."""
    raw = parsed.get("titles")
    if not isinstance(raw, list):
        return None
    cleaned: list[str] = []
    for entry in raw:
        title = _clean_title(entry)
        if title is None:
            continue
        cleaned.append(title)
        if len(cleaned) == _NUM_CANDIDATES:
            break
    if len(cleaned) < _NUM_CANDIDATES:
        return None
    return cleaned


async def _run_query(
    messages: Sequence[dict[str, Any]],
    *,
    model: str,
    query_fn: Any | None = None,
) -> str:
    """Drive the SDK's one-shot `query()` call and concatenate its
    assistant text. Isolated so tests can monkeypatch `query_fn` with
    a fake. The default branch imports the real SDK lazily to keep
    import cost off the hot path of routes that never enable LLM mode.
    Mirrors `_reorg_analyze._run_llm_query`."""
    if query_fn is None:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            TextBlock,
            query,
        )

        options = ClaudeAgentOptions(
            model=model,
            system_prompt=_SYSTEM_PROMPT,
            permission_mode="default",
            max_turns=1,
            setting_sources=None,
        )
        prompt = _build_user_prompt(messages)
        chunks: list[str] = []
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        chunks.append(block.text)
        return "".join(chunks)

    raw = await query_fn(messages)
    return str(raw)


async def suggest_titles(
    messages: Sequence[dict[str, Any]],
    *,
    model: str,
    query_fn: Any | None = None,
) -> tuple[list[str] | None, str]:
    """One-shot title suggester. Returns `(titles, notes)`.

    `titles` is a list of exactly three non-empty strings on success,
    or None when the LLM call failed in a way the caller should
    surface to the UI (parse error, empty response, exception). The
    response NEVER returns an empty list — the system prompt forbids
    it and the validator rejects shorter responses. `notes` is a
    short reason string (empty on success) for the UI to render.

    `query_fn` is the test seam: a coroutine that takes the messages
    sequence and returns the raw response text. Pass None in
    production to use the real SDK."""
    last_error = ""
    for attempt in range(2):
        try:
            text = await _run_query(messages, model=model, query_fn=query_fn)
        except Exception as exc:  # noqa: BLE001
            last_error = f"LLM call failed: {exc!r}"
            logger.warning("suggest_titles attempt %d failed: %r", attempt + 1, exc)
            continue
        parsed = _extract_json_block(text)
        if parsed is None:
            last_error = "LLM returned unparseable JSON"
            logger.warning("suggest_titles attempt %d: unparseable JSON", attempt + 1)
            continue
        validated = _validate_titles(parsed)
        if validated is None:
            last_error = "LLM JSON missing or short 'titles' list"
            logger.warning("suggest_titles attempt %d: shape mismatch", attempt + 1)
            continue
        return validated, ""
    return None, last_error or "title suggester failed"
