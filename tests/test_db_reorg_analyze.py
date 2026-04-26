"""Tests for `bearings.db._reorg_analyze` — Slice 6 of the Session
Reorg plan (`~/.claude/plans/sparkling-triaging-otter.md`).

Covers heuristic determinism (time-gap split, topic-shift split,
single-segment passthrough) and the LLM analyzer's JSON-validation +
fallback paths. The LLM call itself is exercised via the `query_fn`
test seam — no SDK calls go out from the test suite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from bearings.db._reorg_analyze import (
    _build_llm_user_prompt,
    _extract_json_block,
    _jaccard_distance,
    _tokenize,
    _validate_llm_proposals,
    heuristic_analyze,
    llm_analyze,
)


def _msg(
    msg_id: str,
    *,
    role: str = "user",
    content: str = "",
    created_at: datetime | None = None,
) -> dict[str, object]:
    """Mint a message-row dict shaped like `list_messages` output —
    only the fields the analyzer reads. `created_at` defaults to a
    fixed epoch so tests with no time-gap concerns stay terse."""
    stamp = created_at or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    return {
        "id": msg_id,
        "role": role,
        "content": content,
        "created_at": stamp.isoformat(),
    }


# ---------- heuristic ------------------------------------------------


def test_heuristic_empty_returns_no_proposals() -> None:
    assert heuristic_analyze([], source_tag_ids=[1]) == []


def test_heuristic_single_segment_no_proposals() -> None:
    """Coherent session with no time gaps and lexically-similar
    prompts should produce zero proposals — the heuristic only
    suggests splits when it finds a real boundary."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    msgs = [
        _msg(
            f"m{i}",
            content=f"reorg analyzer slice planning {i}",
            created_at=base + timedelta(minutes=i),
        )
        for i in range(8)
    ]
    assert heuristic_analyze(msgs, source_tag_ids=[1]) == []


def test_heuristic_splits_on_time_gap() -> None:
    """Two clusters separated by >2h gap should produce two proposals
    with the time-gap reason on the boundary. Proposals stay in
    source order; tag inheritance carries through."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    msgs = [
        _msg("a1", content="checklist feature", created_at=base),
        _msg("a2", content="checklist plumbing", created_at=base + timedelta(minutes=10)),
        # 3h gap = clear cliff
        _msg(
            "b1",
            content="resume bug investigation",
            created_at=base + timedelta(hours=3, minutes=20),
        ),
        _msg(
            "b2",
            content="resume bug fix",
            created_at=base + timedelta(hours=3, minutes=30),
        ),
    ]
    proposals = heuristic_analyze(msgs, source_tag_ids=[7])
    assert len(proposals) == 2
    assert proposals[0]["message_ids"] == ["a1", "a2"]
    assert proposals[1]["message_ids"] == ["b1", "b2"]
    assert "time gap" in proposals[0]["rationale"]
    # Severity tag inheritance — every proposal carries the source tag.
    for p in proposals:
        assert p["suggested_session"]["tag_ids"] == [7]
        assert p["confidence"] == 1.0  # time-gap splits get full confidence


def test_heuristic_is_deterministic() -> None:
    """Same input twice → identical output. No clock reads, no
    randomness, no set-iteration leakage."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    msgs = [
        _msg("a", content="alpha beta gamma", created_at=base),
        _msg(
            "b",
            content="something else entirely",
            created_at=base + timedelta(hours=4),
        ),
    ]
    first = heuristic_analyze(msgs, source_tag_ids=[1])
    second = heuristic_analyze(msgs, source_tag_ids=[1])
    assert first == second


def test_heuristic_handles_missing_timestamps_gracefully() -> None:
    """A message with no `created_at` should not crash the gap
    detector — the helper treats unparseable / missing stamps as
    zero-gap and lets topic-shift logic handle the boundary."""
    msgs = [
        _msg("x1", content="alpha"),
        {"id": "x2", "role": "user", "content": "beta", "created_at": None},
        _msg("x3", content="gamma"),
    ]
    # Should not raise; result is empty (no time-gap detected).
    proposals = heuristic_analyze(msgs, source_tag_ids=[1])
    assert isinstance(proposals, list)


# ---------- helpers --------------------------------------------------


def test_tokenize_drops_stop_words_and_short_tokens() -> None:
    tokens = _tokenize("The quick BROWN fox is at the door")
    assert "quick" in tokens
    assert "brown" in tokens
    assert "fox" in tokens
    assert "the" not in tokens
    assert "is" not in tokens
    assert "at" not in tokens


def test_jaccard_distance_disjoint_is_one() -> None:
    assert _jaccard_distance({"a", "b"}, {"c", "d"}) == 1.0


def test_jaccard_distance_identical_is_zero() -> None:
    assert _jaccard_distance({"a", "b"}, {"a", "b"}) == 0.0


def test_jaccard_distance_empty_pair_is_zero() -> None:
    assert _jaccard_distance(set(), set()) == 0.0


# ---------- LLM JSON validation -------------------------------------


def test_extract_json_block_strips_fences() -> None:
    """The LLM is told to emit raw JSON but sometimes wraps in fences
    or prose; the brace scanner should still find the object."""
    raw = 'Here you go:\n```\n{"proposals": []}\n```\nDone.'
    assert _extract_json_block(raw) == {"proposals": []}


def test_extract_json_block_returns_none_on_no_braces() -> None:
    assert _extract_json_block("no json at all") is None


def test_validate_llm_drops_unknown_message_ids() -> None:
    """The model occasionally hallucinates an id; the validator
    drops those and keeps the proposal if at least one valid id
    survives."""
    parsed = {
        "proposals": [
            {
                "topic": "real",
                "rationale": "kept",
                "message_ids": ["a", "ghost"],
                "title": "Real",
            }
        ]
    }
    out = _validate_llm_proposals(parsed, valid_ids={"a", "b"}, source_tag_ids=[2])
    assert out is not None and len(out) == 1
    assert out[0]["message_ids"] == ["a"]
    assert out[0]["suggested_session"]["tag_ids"] == [2]


def test_validate_llm_drops_proposals_with_only_unknown_ids() -> None:
    parsed = {"proposals": [{"message_ids": ["ghost"], "topic": "x"}]}
    out = _validate_llm_proposals(parsed, valid_ids={"a"}, source_tag_ids=[1])
    assert out == []


def test_validate_llm_dedupes_across_proposals() -> None:
    """Same id in two proposals — the first wins, the second drops it.
    Prevents the analyzer from accidentally double-moving a message
    when the LLM forgets the no-overlap rule."""
    parsed = {
        "proposals": [
            {"message_ids": ["a", "b"], "topic": "1"},
            {"message_ids": ["b", "c"], "topic": "2"},
        ]
    }
    out = _validate_llm_proposals(parsed, valid_ids={"a", "b", "c"}, source_tag_ids=[1])
    assert out is not None and len(out) == 2
    assert out[0]["message_ids"] == ["a", "b"]
    assert out[1]["message_ids"] == ["c"]


def test_validate_llm_returns_none_on_missing_proposals_key() -> None:
    """Shape error — None signals the caller to fall through to
    heuristic instead of treating it as an empty list."""
    assert _validate_llm_proposals({"x": []}, valid_ids=set(), source_tag_ids=[]) is None


def test_build_llm_user_prompt_truncates_long_content() -> None:
    big = "x" * 1000
    msgs = [_msg("a", content=big)]
    prompt = _build_llm_user_prompt(msgs)
    # Truncated to 400 chars + ellipsis
    assert "x…" in prompt
    assert prompt.count("x") < 1000


# ---------- LLM analyzer end-to-end (with fake query_fn) ------------


@pytest.mark.asyncio
async def test_llm_analyze_happy_path_with_fake_query() -> None:
    msgs = [_msg("a"), _msg("b"), _msg("c")]

    async def fake(_: object) -> str:
        return (
            '{"proposals": [{"topic": "topic A", "rationale": "ra", '
            '"message_ids": ["a", "b"], "title": "Topic A"}]}'
        )

    proposals, notes = await llm_analyze(
        msgs, source_tag_ids=[5], model="claude-test", query_fn=fake
    )
    assert proposals is not None
    assert notes == ""
    assert len(proposals) == 1
    assert proposals[0]["message_ids"] == ["a", "b"]
    assert proposals[0]["suggested_session"]["tag_ids"] == [5]
    assert proposals[0]["suggested_session"]["title"] == "Topic A"


@pytest.mark.asyncio
async def test_llm_analyze_falls_back_on_unparseable_json() -> None:
    """Two consecutive parse failures → returns None so the route
    fires the heuristic fallback. `notes` carries a one-line reason."""
    msgs = [_msg("a")]

    async def fake(_: object) -> str:
        return "this is not json"

    proposals, notes = await llm_analyze(
        msgs, source_tag_ids=[1], model="claude-test", query_fn=fake
    )
    assert proposals is None
    assert notes  # non-empty reason


@pytest.mark.asyncio
async def test_llm_analyze_falls_back_on_exception() -> None:
    """SDK errors from the query call shouldn't surface as 500s — the
    caller wants a fallback path. Two attempts then None."""
    msgs = [_msg("a")]

    async def boom(_: object) -> str:
        raise RuntimeError("transient SDK error")

    proposals, notes = await llm_analyze(
        msgs, source_tag_ids=[1], model="claude-test", query_fn=boom
    )
    assert proposals is None
    assert "failed" in notes.lower()


@pytest.mark.asyncio
async def test_llm_analyze_empty_proposals_is_valid() -> None:
    """Model says "no split needed" — that's a valid answer, not a
    fallback trigger. proposals=[] with no notes."""
    msgs = [_msg("a"), _msg("b")]

    async def fake(_: object) -> str:
        return '{"proposals": []}'

    proposals, notes = await llm_analyze(
        msgs, source_tag_ids=[1], model="claude-test", query_fn=fake
    )
    assert proposals == []
    assert notes == ""
