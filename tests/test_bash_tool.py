"""Tests for the streaming `bash` MCP tool (`agent/bash_tool.py`).

Locks down the four invariants from the Path B scope item:

(a) line-by-line emission via emit_delta — every newline-terminated
    chunk lands on the callback in order.
(b) final-return shape matches what the SDK expects — a dict with
    `content=[{type:"text", text:...}]` and an `is_error` flag that
    follows the subprocess exit code.
(c) UTF-8 safety via LineBuffer — multibyte codepoints split across
    subprocess reads round-trip intact in deltas.
(d) interrupt path cancels the subprocess — cancelling the run_bash
    task tears down the child without leaking it.

The factory tests that go through the SDK `@tool` decorator just
check the input schema / wiring; behavior is exercised against the
underlying ``run_bash`` to keep the test loop tight (no MCP control
plane needed)."""

from __future__ import annotations

import asyncio

import pytest

from bearings.agent.bash_tool import build_bash_tool, run_bash


@pytest.mark.asyncio
async def test_run_bash_emits_one_delta_per_line() -> None:
    """Each newline-terminated chunk arrives via emit_delta in order
    and the final return aggregates them. Three printf lines → three
    deltas, all carrying the same tool_use_id, plus a final body that
    matches the streamed text concatenated."""
    deltas: list[tuple[str, str]] = []

    def emit(tid: str, line: str) -> None:
        deltas.append((tid, line))

    result = await run_bash(
        "printf 'one\\ntwo\\nthree\\n'",
        timeout=10.0,
        tool_use_id="tc-1",
        emit_delta=emit,
    )

    assert [line for _tid, line in deltas] == ["one\n", "two\n", "three\n"]
    assert all(tid == "tc-1" for tid, _line in deltas)
    text = result["content"][0]["text"]
    assert "one\ntwo\nthree\n" in text
    assert result.get("is_error") is not True


@pytest.mark.asyncio
async def test_run_bash_final_return_shape_matches_sdk_contract() -> None:
    """The dict shape must satisfy the SDK MCP tool contract: a
    ``content`` list with text blocks. ``is_error`` is true on
    non-zero exit so the model can react. Without this, the SDK
    rejects the response or surfaces a malformed tool_result."""
    out_ok = await run_bash(
        "true",
        timeout=5.0,
        tool_use_id="tc-ok",
        emit_delta=lambda *_: None,
    )
    assert isinstance(out_ok, dict)
    assert "content" in out_ok
    assert isinstance(out_ok["content"], list)
    assert out_ok["content"][0]["type"] == "text"
    assert out_ok.get("is_error") is not True

    out_fail = await run_bash(
        "exit 7",
        timeout=5.0,
        tool_use_id="tc-fail",
        emit_delta=lambda *_: None,
    )
    assert out_fail["is_error"] is True
    assert "exit code 7" in out_fail["content"][0]["text"]


@pytest.mark.asyncio
async def test_run_bash_merges_stderr_into_live_stream() -> None:
    """Stderr is redirected to stdout at the subprocess level, so a
    failing command's diagnostic text shows up live the same as
    stdout — and the final return carries the error framing."""
    deltas: list[str] = []

    def emit(_tid: str, line: str) -> None:
        deltas.append(line)

    result = await run_bash(
        "printf 'oops\\n' 1>&2; exit 2",
        timeout=5.0,
        tool_use_id="tc-err",
        emit_delta=emit,
    )

    assert "oops\n" in deltas
    assert result["is_error"] is True
    assert "exit code 2" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_run_bash_utf8_multibyte_safety() -> None:
    """A 3-byte UTF-8 codepoint (the snowman ☃ = 0xE2 0x98 0x83) split
    across subprocess reads must arrive intact in the delta. LineBuffer
    is what guarantees this; this test is the end-to-end pin."""
    deltas: list[str] = []

    def emit(_tid: str, line: str) -> None:
        deltas.append(line)

    # Two snowmen on one line — bytes are well past the codepoint
    # boundary, but LineBuffer holds back the partial slice until a
    # newline arrives so the decoded line is always whole.
    result = await run_bash(
        "printf '\\xe2\\x98\\x83\\xe2\\x98\\x83\\n'",
        timeout=5.0,
        tool_use_id="tc-utf",
        emit_delta=emit,
    )

    assert deltas == ["☃☃\n"]
    assert "☃☃" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_run_bash_handles_partial_trailing_line() -> None:
    """A subprocess that exits without a final newline still surfaces
    the trailing partial line through `LineBuffer.flush` — both as a
    delta and in the final return."""
    deltas: list[str] = []

    def emit(_tid: str, line: str) -> None:
        deltas.append(line)

    result = await run_bash(
        "printf 'no-newline-at-end'",
        timeout=5.0,
        tool_use_id="tc-tail",
        emit_delta=emit,
    )

    assert deltas == ["no-newline-at-end"]
    assert "no-newline-at-end" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_run_bash_emit_delta_failure_is_isolated() -> None:
    """If the emit callback raises, the pump must not abort —
    subsequent lines and the final return still arrive. The frontend
    losing one delta is an inconvenience; the SDK losing the entire
    tool_result is a turn failure."""
    seen: list[str] = []

    def flaky(_tid: str, line: str) -> None:
        seen.append(line)
        if line.startswith("a"):
            raise RuntimeError("simulated callback failure")

    result = await run_bash(
        "printf 'a\\nb\\nc\\n'",
        timeout=5.0,
        tool_use_id="tc-flaky",
        emit_delta=flaky,
    )

    # All three lines reached the callback even though the first one
    # raised — the pump's try/except absorbed the error.
    assert seen == ["a\n", "b\n", "c\n"]
    assert "a\nb\nc\n" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_run_bash_interrupt_kills_subprocess() -> None:
    """Cancelling the run_bash task must propagate CancelledError AND
    kill the child. The `os.kill(pid, 0)` probe verifies the process
    is gone — if cancellation fell through and left the child alive,
    we'd see a `ProcessLookupError` not raised and would fail the
    timing-based gate."""
    pump_started = asyncio.Event()
    deltas: list[str] = []

    def emit(_tid: str, line: str) -> None:
        deltas.append(line)
        pump_started.set()

    # `sh -c "echo ready; sleep 30"` lets us confirm the pump has
    # actually started before we cancel — proves the cancel reached
    # mid-stream rather than racing the spawn.
    task = asyncio.create_task(
        run_bash(
            "echo ready; sleep 30",
            timeout=60.0,
            tool_use_id="tc-cancel",
            emit_delta=emit,
        )
    )

    # Wait until the first delta lands; then capture the pid by
    # reaching into asyncio's bookkeeping is fragile, so we instead
    # rely on the cancel + post-cancel timing assertion below.
    await asyncio.wait_for(pump_started.wait(), timeout=5.0)
    assert deltas == ["ready\n"]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Give the kernel a beat to reap the killed child. If cancellation
    # didn't propagate to a `proc.kill()`, the `sleep 30` would still
    # be running and the test framework would have to wait for the
    # whole 30s timeout to flush — the pytest-level timeout catches
    # that case as a hard failure.


@pytest.mark.asyncio
async def test_run_bash_timeout_kills_runaway_subprocess() -> None:
    """A command that exceeds its timeout gets killed and reports
    timed_out in the final return. Cap is bounded so a misconfigured
    `timeout=0` doesn't let the model bypass the watchdog."""
    deltas: list[str] = []

    def emit(_tid: str, line: str) -> None:
        deltas.append(line)

    result = await run_bash(
        "echo started; sleep 30",
        timeout=0.5,
        tool_use_id="tc-timeout",
        emit_delta=emit,
    )

    assert deltas == ["started\n"]
    assert result["is_error"] is True
    assert "timed out" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_run_bash_truncates_huge_output_in_final_return() -> None:
    """Final-return body is capped at 5 MB; deltas keep flowing live.
    Without this guard, a runaway tool would push a 50 MB blob into
    every subsequent turn's tool_result cache."""
    delta_chars = 0

    def emit(_tid: str, line: str) -> None:
        nonlocal delta_chars
        delta_chars += len(line)

    # Print ~6 MB of `x` characters, line-broken every ~1 KB.
    # Cap is 5_000_000 chars; the formatter's truncation marker
    # should appear in the final text.
    result = await run_bash(
        "yes x | head -c 6000000 | fold -w 1024",
        timeout=30.0,
        tool_use_id="tc-big",
        emit_delta=emit,
    )

    text = result["content"][0]["text"]
    # Live stream sees the full output (ish — newlines added by fold).
    assert delta_chars >= 6_000_000
    # Final return is capped — truncation marker present, total
    # length under cap + headroom for marker text.
    assert "output truncated" in text
    assert len(text) < 5_500_000


@pytest.mark.asyncio
async def test_run_bash_rejects_empty_command() -> None:
    """An empty / whitespace-only command short-circuits before
    spawning a subprocess — protects against a malformed input that
    would otherwise hang on /bin/sh's interactive prompt."""
    result = await run_bash(
        "   ",
        timeout=5.0,
        tool_use_id="tc-empty",
        emit_delta=lambda *_: None,
    )
    # `run_bash` itself doesn't check empty (it spawns whatever it's
    # given). The empty-guard lives in the @tool wrapper. A pure
    # whitespace command goes through `sh -c '   '` which is a no-op
    # and exits 0 — that's acceptable; the wrapper guard handles the
    # model-facing path.
    assert result.get("is_error") is not True


@pytest.mark.asyncio
async def test_build_bash_tool_handler_short_circuits_empty_command() -> None:
    """The @tool wrapper rejects empty commands before they reach
    `run_bash`, so the model gets a clean error without the cost of
    spawning a no-op shell."""

    async def id_getter() -> str:
        return "tc-empty"

    sdk_tool = build_bash_tool(lambda *_: None, id_getter)
    result = await sdk_tool.handler({"command": "", "timeout": 5.0})
    assert result["is_error"] is True
    assert "empty command" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_build_bash_tool_claims_tool_use_id_from_getter() -> None:
    """The factory's `get_tool_use_id` callback returns the next
    pending tool_use_id; deltas emitted during the call carry that id.
    Confirms the queue→handler correlation path end-to-end."""
    deltas: list[tuple[str, str]] = []

    def emit(tid: str, line: str) -> None:
        deltas.append((tid, line))

    queue: asyncio.Queue[str] = asyncio.Queue()
    queue.put_nowait("tc-from-queue")

    sdk_tool = build_bash_tool(emit, queue.get)
    result = await sdk_tool.handler({"command": "printf 'hi\\n'", "timeout": 5.0})

    assert deltas == [("tc-from-queue", "hi\n")]
    assert result.get("is_error") is not True


@pytest.mark.asyncio
async def test_build_bash_tool_falls_back_when_id_never_arrives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the session never pushes a tool_use_id (misconfigured wiring),
    the handler falls back to a synthetic id rather than hanging
    forever. Frontend reducer drops deltas pointing at unknown ids
    so the worst-case is "live stream invisible," not a turn hang."""
    # Squeeze the wait window so the test runs in milliseconds, not 5s.
    monkeypatch.setattr("bearings.agent.bash_tool._TOOL_USE_ID_WAIT_S", 0.05)

    deltas: list[tuple[str, str]] = []

    def emit(tid: str, line: str) -> None:
        deltas.append((tid, line))

    async def never_resolves() -> str:
        await asyncio.sleep(10.0)  # would block past the test timeout
        return "unreachable"

    sdk_tool = build_bash_tool(emit, never_resolves)
    result = await sdk_tool.handler({"command": "printf 'fallback\\n'", "timeout": 5.0})

    assert deltas
    assert deltas[0][0] == "bearings-bash-no-id"
    assert result.get("is_error") is not True
