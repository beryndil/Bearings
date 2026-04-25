"""Bearings-owned `bash` MCP tool with line-by-line output streaming.

The model's built-in `Bash` tool returns one final `tool_result` block
when the command exits — fine for short invocations, opaque for a long
`npm run build` or `grep -rn ...` where the user wants to see output as
it lands. This module registers a drop-in replacement via the SDK MCP
server: same conceptual interface (a ``command`` plus optional
``timeout``), but every line of stdout/stderr fans out as a
``ToolOutputDelta`` event through an injected callback as the
subprocess produces it. The final return still satisfies the SDK's
tool-result contract — the combined output text plus exit-code framing
— so the model sees the same surface it would from the built-in Bash on
completion.

Bytes go through `LineBuffer` so multibyte UTF-8 codepoints and ANSI
escape sequences never split mid-sequence across deltas. Stderr is
merged into stdout at subprocess level so live ordering matches what
a human would see in a terminal.

**Tool-use-id correlation.** The MCP `tools/call` payload doesn't
carry the model's `tool_use.id`, so the session pre-registers an id
on a queue when it observes the matching `ToolCallStart` block, and
the handler claims the next id on entry. The session-side wiring lives
in `agent/session.py`. Side-effect: parallel bash calls within a
single assistant message get matched in receipt order, which is
acceptable since the model effectively serialises tool calls anyway.

Module is safe to import even in test environments that mock the SDK
— `build_bash_tool` is the only public entry point and it only
references the SDK's ``@tool`` decorator at call time.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from claude_agent_sdk import tool

from bearings.agent.line_buffer import LineBuffer

log = logging.getLogger(__name__)


# Synchronous on purpose: the session-side implementation does
# ``queue.put_nowait`` which never blocks. Keeping the callback sync
# means the bash handler's hot loop never has to ``await`` per line —
# a long ``grep -r`` emitting tens of thousands of lines would otherwise
# spam the event loop with one extra task per line.
EmitDelta = Callable[[str, str], None]
ToolUseIdGetter = Callable[[], Awaitable[str]]


# Default per-call timeout in seconds. The model's input may override
# (capped at the upper bound). Mirrors Claude Code's built-in Bash tool
# default — long enough for most builds, short enough that an
# unintentional infinite loop doesn't strand a session indefinitely.
_DEFAULT_TIMEOUT_S = 120.0
_MAX_TIMEOUT_S = 600.0

# Cap the combined output kept in memory for the FINAL return. Anything
# beyond this is dropped from the returned text — the live stream
# already delivered it to the client. Matches the frontend reducer's
# ``TOOL_OUTPUT_CAP_CHARS`` so the persisted "head + truncation" notice
# stays within the same envelope as the live stream.
_FINAL_OUTPUT_CAP = 5_000_000

# Time budget for the session to push the corresponding tool_use_id
# onto the pending queue before we give up and use a synthetic id.
# Should be tiny in practice — receive_response runs ahead of the SDK's
# call_tool dispatch — but bounded so a misconfigured session can't
# leave the handler hanging forever.
_TOOL_USE_ID_WAIT_S = 5.0

# Final time budget for draining any subprocess output that arrived
# between SIGKILL and process exit. After this, the pump task is
# cancelled and the partial body is returned as-is.
_PUMP_DRAIN_S = 2.0

# Read chunk size for stdout. Tuned for reasonable batching without
# starving the live stream — at 4 KB a moderately chatty tool produces
# multiple deltas per second instead of one giant final dump.
_READ_CHUNK = 4096


def build_bash_tool(emit_delta: EmitDelta, get_tool_use_id: ToolUseIdGetter) -> Any:
    """Construct the `bash` MCP tool. Factory shape mirrors
    `_build_get_tool_output` in `mcp_tools.py` — the closure captures
    the injected emit + id-getter so unit tests can construct a fresh
    handler without involving the SDK control plane."""

    @tool(
        "bash",
        (
            "Execute a shell command. Same interface as the built-in "
            "Bash tool, but Bearings streams stdout/stderr live to the "
            "session terminal pane line-by-line as the command runs "
            "(the built-in Bash returns one final block on exit). "
            "Returns the combined output and exit-code framing on "
            "completion. Prefer this over the built-in Bash for any "
            "shell, build, grep, find, or git command — live output is "
            "what makes long commands actually watchable."
        ),
        {"command": str, "timeout": float},
    )
    async def bash(args: dict[str, Any]) -> dict[str, Any]:
        command = str(args.get("command") or "").strip()
        if not command:
            return {
                "content": [{"type": "text", "text": "bearings.bash: empty command"}],
                "is_error": True,
            }
        timeout_raw = args.get("timeout")
        try:
            timeout = float(timeout_raw) if timeout_raw is not None else _DEFAULT_TIMEOUT_S
        except (TypeError, ValueError):
            timeout = _DEFAULT_TIMEOUT_S
        timeout = min(max(timeout, 0.1), _MAX_TIMEOUT_S)
        tool_use_id = await _wait_for_tool_use_id(get_tool_use_id)
        return await run_bash(command, timeout, tool_use_id, emit_delta)

    return bash


async def _wait_for_tool_use_id(getter: ToolUseIdGetter) -> str:
    """Pull the next pending bash tool_use_id from the session, with a
    bounded wait. Falls back to a synthetic id if nothing arrives in
    time so a misconfigured session can't strand the subprocess. The
    frontend reducer drops deltas pointing at unknown ids, so the cost
    of the synthetic-id branch is "live stream invisible for this one
    call" — never a crash."""
    try:
        return await asyncio.wait_for(getter(), timeout=_TOOL_USE_ID_WAIT_S)
    except TimeoutError:
        log.warning(
            "bearings.bash: no tool_use_id arrived within %.1fs; "
            "emitting deltas under synthetic id",
            _TOOL_USE_ID_WAIT_S,
        )
        return "bearings-bash-no-id"


async def run_bash(
    command: str,
    timeout: float,
    tool_use_id: str,
    emit_delta: EmitDelta,
) -> dict[str, Any]:
    """Spawn a shell, stream lines via emit_delta, return the combined
    output dict the SDK expects.

    Stdout and stderr are merged into a single stream (stderr → stdout
    at subprocess level) so live order matches what a user would see in
    a terminal. The returned text caps at ``_FINAL_OUTPUT_CAP`` chars;
    bytes beyond the cap stream live but don't bloat the SDK return.
    """
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout = proc.stdout
    if stdout is None:
        # Defensive — PIPE was requested above, so this should never
        # happen, but the type is `StreamReader | None`.
        await proc.wait()
        return _format_result([], 0, None, proc.returncode, False, timeout)

    state = _PumpState()

    async def pump() -> None:
        buf = LineBuffer()
        try:
            while True:
                chunk = await stdout.read(_READ_CHUNK)
                if not chunk:
                    break
                for line in buf.feed(chunk):
                    state.absorb(line, tool_use_id, emit_delta)
            tail = buf.flush()
            if tail:
                state.absorb(tail, tool_use_id, emit_delta)
        except asyncio.CancelledError:
            # Don't swallow — the caller (run_bash) needs to know the
            # pump was cancelled so it can stop waiting.
            raise

    pump_task = asyncio.create_task(pump())
    timed_out = False
    try:
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except TimeoutError:
            timed_out = True
            _kill_proc(proc)
            with contextlib.suppress(asyncio.CancelledError, OSError):
                await proc.wait()
        # Drain whatever the subprocess emitted before exit/kill.
        try:
            await asyncio.wait_for(pump_task, timeout=_PUMP_DRAIN_S)
        except TimeoutError:
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pump_task
    except asyncio.CancelledError:
        # The session is cancelling us (interrupt path). Kill the
        # subprocess, cancel the pump, and re-raise so the SDK / runner
        # can wind down cleanly.
        _kill_proc(proc)
        pump_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, OSError):
            await pump_task
        with contextlib.suppress(OSError):
            await proc.wait()
        raise

    return _format_result(
        state.chunks,
        state.accumulated_chars,
        state.truncated_at,
        proc.returncode,
        timed_out,
        timeout,
    )


class _PumpState:
    """Mutable state shared between the subprocess pump and the result
    formatter. Lives only for the duration of one ``run_bash`` call.

    Owns the in-memory cap accounting so the pump can stop appending
    to ``chunks`` once we exceed ``_FINAL_OUTPUT_CAP`` without losing
    the live stream — deltas keep flowing, only the final-return body
    gets head-truncated."""

    __slots__ = ("chunks", "accumulated_chars", "truncated_at")

    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.accumulated_chars: int = 0
        # Total observed length at the moment we tipped past the cap.
        # `None` until that happens so the formatter can distinguish
        # "well within budget" from "truncated."
        self.truncated_at: int | None = None

    def absorb(self, line: str, tool_use_id: str, emit_delta: EmitDelta) -> None:
        _try_emit(emit_delta, tool_use_id, line)
        if self.truncated_at is not None:
            # Already past the cap — count for the marker but don't
            # retain the bytes.
            self.truncated_at += len(line)
            return
        if self.accumulated_chars + len(line) <= _FINAL_OUTPUT_CAP:
            self.chunks.append(line)
            self.accumulated_chars += len(line)
            return
        # First line that crosses the cap — keep prior chunks, drop
        # this line, mark the truncation point.
        self.truncated_at = self.accumulated_chars + len(line)


def _try_emit(emit_delta: EmitDelta, tool_use_id: str, line: str) -> None:
    """Best-effort emit — a misbehaving callback must not abort the
    subprocess pump. Surface the failure in logs and continue
    streaming; the final return still carries the text."""
    try:
        emit_delta(tool_use_id, line)
    except Exception:  # noqa: BLE001 — callback isolation
        log.exception("bearings.bash: emit_delta callback raised; continuing")


def _kill_proc(proc: asyncio.subprocess.Process) -> None:
    """Best-effort kill. ProcessLookupError = already exited; OSError
    covers transient errno conditions on the kernel side. Either way,
    the wait() that follows will reap the zombie."""
    with contextlib.suppress(ProcessLookupError, OSError):
        proc.kill()


def _format_result(
    chunks: list[str],
    written_chars: int,
    truncated_at: int | None,
    returncode: int | None,
    timed_out: bool,
    timeout: float,
) -> dict[str, Any]:
    body = "".join(chunks)
    parts: list[str] = []
    if truncated_at is not None:
        parts.append(
            f"[bearings.bash: output truncated — kept first {written_chars} of "
            f"{truncated_at}+ chars; full text was streamed live]\n"
        )
    parts.append(body)
    if timed_out:
        parts.append(f"\n[bearings.bash: timed out after {timeout:.1f}s, process killed]")
    elif returncode is not None and returncode != 0:
        parts.append(f"\n[bearings.bash: exit code {returncode}]")
    text = "".join(parts) or "(no output)"
    is_error = timed_out or (returncode is not None and returncode != 0)
    return {
        "content": [{"type": "text", "text": text}],
        "is_error": is_error,
    }
