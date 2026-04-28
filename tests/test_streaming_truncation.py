"""Truncation tests — :mod:`bearings.agent.runner` chunking + hard cap.

Covers the behavior-doc §"Very-long-output truncation rules" surface:

* **Chunking.** A :class:`ToolOutputDelta` whose payload exceeds
  :data:`STREAM_MAX_DELTA_CHARS` is split into multiple events at
  codepoint-safe boundaries; total payload is preserved.
* **Hard cap on persistence.** Per-tool cumulative output beyond
  :data:`STREAM_MAX_TOOL_OUTPUT_CHARS` is dropped, with a single
  truncation marker delta appended at the end. Per behavior doc:
  "the marker always appears at the end of the persisted body, never
  in the middle."
* **Reset on ``ToolCallEnd``.** A subsequent tool call with the same
  ``tool_call_id`` (rare) resets the counter so it doesn't inherit
  the prior call's already-truncated state.
* **Multi-byte safety.** Codepoint boundaries — Python ``str`` slicing
  is codepoint-indexed, so the chunker can't split a multibyte
  codepoint mid-sequence.
"""

from __future__ import annotations

import pytest

from bearings.agent.events import (
    ToolCallEnd,
    ToolCallStart,
    ToolOutputDelta,
)
from bearings.agent.runner import SessionRunner
from bearings.config.constants import (
    STREAM_MAX_DELTA_CHARS,
    STREAM_MAX_TOOL_OUTPUT_CHARS,
    STREAM_TRUNCATION_MARKER_TEMPLATE,
)

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delta_below_cap_publishes_one_event() -> None:
    runner = SessionRunner("s1")
    payload = "x" * (STREAM_MAX_DELTA_CHARS - 1)
    await runner.emit(ToolOutputDelta(session_id="s1", tool_call_id="tc1", delta=payload))
    deltas = _all_deltas(runner)
    assert len(deltas) == 1
    assert deltas[0].delta == payload


@pytest.mark.asyncio
async def test_delta_at_exact_cap_publishes_one_event() -> None:
    runner = SessionRunner("s1")
    payload = "x" * STREAM_MAX_DELTA_CHARS
    await runner.emit(ToolOutputDelta(session_id="s1", tool_call_id="tc1", delta=payload))
    deltas = _all_deltas(runner)
    assert len(deltas) == 1
    assert len(deltas[0].delta) == STREAM_MAX_DELTA_CHARS


@pytest.mark.asyncio
async def test_oversized_delta_splits_preserving_payload() -> None:
    """A 2.5xcap payload splits into 3 chunks; concatenation == original."""
    runner = SessionRunner("s1")
    payload = "y" * (STREAM_MAX_DELTA_CHARS * 2 + STREAM_MAX_DELTA_CHARS // 2)
    await runner.emit(ToolOutputDelta(session_id="s1", tool_call_id="tc1", delta=payload))
    deltas = _all_deltas(runner)
    assert len(deltas) == 3
    assert "".join(d.delta for d in deltas) == payload
    # Each non-final chunk is exactly the cap; final chunk is the
    # remainder.
    assert len(deltas[0].delta) == STREAM_MAX_DELTA_CHARS
    assert len(deltas[1].delta) == STREAM_MAX_DELTA_CHARS
    assert len(deltas[2].delta) == STREAM_MAX_DELTA_CHARS // 2


@pytest.mark.asyncio
async def test_chunking_preserves_unicode_codepoints() -> None:
    """Multi-byte codepoints survive the chunker — no mojibake.

    Python ``str`` indexing is codepoint-indexed, so splitting at
    arbitrary indices is safe by language guarantee. This test is the
    audit-friendly receipt for that fact at the runner-emit boundary.
    """
    runner = SessionRunner("s1")
    payload = "🦀" * STREAM_MAX_DELTA_CHARS  # each crab is 1 codepoint
    await runner.emit(ToolOutputDelta(session_id="s1", tool_call_id="tc1", delta=payload))
    deltas = _all_deltas(runner)
    rejoined = "".join(d.delta for d in deltas)
    assert rejoined == payload
    # Every chunk is itself a valid str of crab codepoints.
    for d in deltas:
        assert all(ch == "🦀" for ch in d.delta)


# ---------------------------------------------------------------------------
# Hard cap + truncation marker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hard_cap_appends_marker_and_drops_rest() -> None:
    """A delta exceeding the hard cap is trimmed; marker appended."""
    runner = SessionRunner("s1")
    over_cap = "z" * (STREAM_MAX_TOOL_OUTPUT_CHARS + 5_000)
    await runner.emit(ToolOutputDelta(session_id="s1", tool_call_id="tc1", delta=over_cap))
    deltas = _all_deltas(runner)
    rejoined = "".join(d.delta for d in deltas)
    # Body is exactly cap chars + marker.
    expected_marker = STREAM_TRUNCATION_MARKER_TEMPLATE.format(n=5_000)
    body = rejoined[:STREAM_MAX_TOOL_OUTPUT_CHARS]
    tail = rejoined[STREAM_MAX_TOOL_OUTPUT_CHARS:]
    assert body == "z" * STREAM_MAX_TOOL_OUTPUT_CHARS
    assert tail == expected_marker


@pytest.mark.asyncio
async def test_hard_cap_marker_is_at_end_not_middle() -> None:
    """Per behavior doc: marker is at the END of the persisted body."""
    runner = SessionRunner("s1")
    over_cap = "z" * (STREAM_MAX_TOOL_OUTPUT_CHARS + 100)
    await runner.emit(ToolOutputDelta(session_id="s1", tool_call_id="tc1", delta=over_cap))
    deltas = _all_deltas(runner)
    rejoined = "".join(d.delta for d in deltas)
    # The marker substring appears exactly once and at the very end.
    marker = STREAM_TRUNCATION_MARKER_TEMPLATE.format(n=100)
    assert rejoined.count(marker) == 1
    assert rejoined.endswith(marker)


@pytest.mark.asyncio
async def test_subsequent_deltas_after_truncation_are_dropped() -> None:
    """Once the hard-cap marker fires, further deltas for the same
    ``tool_call_id`` are silently dropped (the marker stays the
    last thing in the body)."""
    runner = SessionRunner("s1")
    await runner.emit(
        ToolOutputDelta(
            session_id="s1",
            tool_call_id="tc1",
            delta="a" * (STREAM_MAX_TOOL_OUTPUT_CHARS + 10),
        )
    )
    seq_after_truncate = runner.last_seq
    # Drop attempt — should not append any new delta event.
    await runner.emit(ToolOutputDelta(session_id="s1", tool_call_id="tc1", delta="b" * 100))
    assert runner.last_seq == seq_after_truncate


@pytest.mark.asyncio
async def test_tool_call_end_resets_truncation_state() -> None:
    """``ToolCallEnd`` resets the per-tool counter so a future tool call
    with the same id starts fresh — no inherited truncation state."""
    runner = SessionRunner("s1")
    # Truncate first call.
    await runner.emit(
        ToolOutputDelta(
            session_id="s1",
            tool_call_id="tc1",
            delta="a" * (STREAM_MAX_TOOL_OUTPUT_CHARS + 10),
        )
    )
    # End the tool call.
    await runner.emit(
        ToolCallEnd(
            session_id="s1",
            message_id="m1",
            tool_call_id="tc1",
            ok=True,
            duration_ms=1,
            output_summary="ok",
        )
    )
    # Second call same id — re-emits delta should pass through.
    await runner.emit(ToolOutputDelta(session_id="s1", tool_call_id="tc1", delta="fresh"))
    deltas_after_end = [
        e
        for _seq, e in list(runner._buffer)
        if isinstance(e, ToolOutputDelta) and e.delta == "fresh"
    ]
    assert len(deltas_after_end) == 1


@pytest.mark.asyncio
async def test_separate_tool_call_ids_have_separate_caps() -> None:
    """Each ``tool_call_id`` has its own counter — exhausting one does
    not affect another."""
    runner = SessionRunner("s1")
    # Truncate tc1.
    await runner.emit(
        ToolOutputDelta(
            session_id="s1",
            tool_call_id="tc1",
            delta="a" * (STREAM_MAX_TOOL_OUTPUT_CHARS + 1),
        )
    )
    # tc2 should still accept output.
    await runner.emit(ToolOutputDelta(session_id="s1", tool_call_id="tc2", delta="hello"))
    tc2_deltas = [
        e
        for _seq, e in list(runner._buffer)
        if isinstance(e, ToolOutputDelta) and e.tool_call_id == "tc2"
    ]
    assert len(tc2_deltas) == 1
    assert tc2_deltas[0].delta == "hello"


# ---------------------------------------------------------------------------
# Non-tool-output events untouched by truncation logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_tool_output_events_pass_through_unchanged() -> None:
    """Truncation logic is scoped to :class:`ToolOutputDelta`; other
    events publish 1:1 regardless of payload size."""
    runner = SessionRunner("s1")
    big_token = "x" * (STREAM_MAX_DELTA_CHARS + 100)
    from bearings.agent.events import Token

    await runner.emit(Token(session_id="s1", message_id="m1", delta=big_token))
    tokens = [e for _seq, e in list(runner._buffer) if isinstance(e, Token)]
    assert len(tokens) == 1
    assert tokens[0].delta == big_token


@pytest.mark.asyncio
async def test_tool_call_start_passes_through_unchanged() -> None:
    runner = SessionRunner("s1")
    await runner.emit(
        ToolCallStart(
            session_id="s1",
            message_id="m1",
            tool_call_id="tc1",
            tool_name="Bash",
            tool_input_json='{"command": "ls"}',
        )
    )
    assert runner.ring_buffer_size == 1
    assert runner.last_seq == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_deltas(runner: SessionRunner) -> list[ToolOutputDelta]:
    return [event for _seq, event in list(runner._buffer) if isinstance(event, ToolOutputDelta)]
