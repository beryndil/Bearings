"""Tests for `bearings.agent.lockout_callback`.

Audit item #519: when the global `~/.claude/hooks/lockout.py` PreToolUse
hook denies a Write/Edit/MultiEdit/NotebookEdit, the SDK's "STOP"
deny-tail halts an autonomous executor session silently — no BLOCKED
callback reaches the orchestrator, the audit stalls until a human
notices. Fix: detect the deny in the runner's post-tool-use event arm
and synthesize a BLOCKED callback to the orchestrator's prompt queue.

These tests pin three contracts:

  1. Lockout deny + executor with `Orchestrator: <id>` in
     `session_instructions` → `prompt_dispatch` is called once with
     `(orchestrator_id, "BLOCKED — ...")`. The happy path that the
     2026-04-27 audit-#384 incident would have wanted.
  2. Lockout deny + executor with no orchestrator hint → no callback;
     executor halts as today. Stand-alone bug sessions must not
     regress (no orchestrator to wake).
  3. Non-lockout tool failure → no callback. The sniffer is
     conservative; it must not fire on ordinary `is_error=True` tool
     results (which happen all the time on syntax-checked Edits etc.).

Fixtures mirror `tests/test_agent_artifacts.py`'s `ScriptedAgent` shape:
single turn per test, real sqlite DB, the runner driven through one
`submit_prompt` end-to-end.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiosqlite
import pytest

from bearings.agent.events import (
    AgentEvent,
    MessageComplete,
    MessageStart,
    ToolCallEnd,
    ToolCallStart,
)
from bearings.agent.lockout_callback import (
    LOCKED_TOOLS,
    LOCKOUT_PREFIX,
    _extract_orchestrator_id,
    _summarize_deny,
)
from bearings.agent.runner import SessionRunner
from bearings.agent.session import AgentSession
from bearings.db import store
from bearings.db._common import init_db


class ScriptedAgent(AgentSession):
    """Minimal stub from `test_runner.py`: one event-list per turn."""

    def __init__(self, session_id: str, scripts: list[list[AgentEvent]]) -> None:
        super().__init__(session_id, working_dir="/tmp", model="m")
        self._scripts = scripts
        self.prompts: list[str] = []

    async def stream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        self.prompts.append(prompt)
        script = self._scripts.pop(0) if self._scripts else []
        for event in script:
            yield event


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    """Real sqlite + one executor session and one orchestrator session.
    Per-test DB so `prompt_dispatch` assertions don't bleed across
    cases."""
    conn = await init_db(tmp_path / "lockout-deny.sqlite")
    # Orchestrator (created first so its id is stable for instructions).
    orch = await store.create_session(conn, working_dir="/tmp", model="m", title="orchestrator")
    # Executor — instructions wired per
    # `~/.claude/rules/executor-handoff-on-pressure.md` §"Wiring".
    exec_row = await store.create_session(conn, working_dir="/tmp", model="m", title="executor")
    await store.update_session(
        conn,
        exec_row["id"],
        fields={
            "session_instructions": (
                f"Master: master-id\nOrchestrator: {orch['id']}\nItem: #519\n"
            ),
        },
    )
    yield conn
    await conn.close()


async def _ids(conn: aiosqlite.Connection) -> tuple[str, str]:
    """Return (executor_id, orchestrator_id) — fixture inserts orch
    first, executor second."""
    rows = await store.list_sessions(conn)
    rows_sorted = sorted(rows, key=lambda r: r["created_at"])
    orch_id = rows_sorted[0]["id"]
    exec_id = rows_sorted[1]["id"]
    return exec_id, orch_id


def _deny_script(
    sid: str,
    *,
    tool_name: str,
    error: str,
) -> list[AgentEvent]:
    """5-event turn: MessageStart → ToolCallStart → failed ToolCallEnd
    → MessageComplete. Mirrors what the SDK emits when a PreToolUse
    hook denies a tool: a synthetic tool result with `is_error=True`
    and the deny `message` in the `error` field of the Bearings
    `ToolCallEnd` translation (per `_events_mixin._tool_call_end`)."""
    return [
        MessageStart(session_id=sid, message_id="msg-1"),
        ToolCallStart(
            session_id=sid,
            tool_call_id="tool-1",
            name=tool_name,
            input={"file_path": "/some/path"},
        ),
        ToolCallEnd(
            session_id=sid,
            tool_call_id="tool-1",
            ok=False,
            output=None,
            error=error,
        ),
        MessageComplete(session_id=sid, message_id="msg-1", cost_usd=None),
    ]


async def _drain_until_complete(queue: asyncio.Queue[Any], timeout: float = 2.0) -> None:
    """Pull envelopes off the subscriber queue until `message_complete`
    arrives. Used purely as a sync-point so the test asserts after the
    runner's worker has processed the ToolCallEnd arm in full."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise AssertionError("message_complete did not arrive within timeout")
        env = await asyncio.wait_for(queue.get(), timeout=remaining)
        if env.payload["type"] == "message_complete":
            return


async def _run_one_turn(runner: SessionRunner, prompt: str = "do it") -> None:
    queue, _ = await runner.subscribe(0)
    runner.start()
    try:
        await runner.submit_prompt(prompt)
        await _drain_until_complete(queue)
    finally:
        await runner.shutdown()


# ---- pure-helper unit tests ----------------------------------------


def test_extract_orchestrator_id_happy() -> None:
    text = "Master: aaaa\nOrchestrator: 33befa3dd7c44c5da62554b01defaf96\nItem: #519\n"
    assert _extract_orchestrator_id(text) == "33befa3dd7c44c5da62554b01defaf96"


def test_extract_orchestrator_id_missing() -> None:
    assert _extract_orchestrator_id("Master: x\nItem: y\n") is None
    assert _extract_orchestrator_id("") is None
    assert _extract_orchestrator_id(None) is None


def test_summarize_deny_strips_prefix_and_keeps_first_line() -> None:
    msg = (
        "[lockout] You are a reader on /home/beryndil/Projects/Bearings.\n"
        "Run `/lockout claim-writer` to take over.\n"
    )
    assert _summarize_deny(msg) == "You are a reader on /home/beryndil/Projects/Bearings."


def test_locked_tools_match_hook_matcher() -> None:
    # Tripwire: if the hook's PreToolUse `matcher` list grows, this set
    # has to grow too or the callback path silently stops firing.
    assert LOCKED_TOOLS == frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
    assert LOCKOUT_PREFIX == "[lockout] "


# ---- end-to-end runner tests ---------------------------------------


@pytest.mark.asyncio
async def test_lockout_deny_posts_blocked_callback(
    db: aiosqlite.Connection,
) -> None:
    """Happy path: `Write` denied with a `[lockout] ...` message →
    `prompt_dispatch` is called exactly once with the orchestrator id
    and a BLOCKED-prefixed content line carrying the tool name and the
    deny reason."""
    exec_id, orch_id = await _ids(db)

    calls: list[tuple[str, str]] = []

    async def fake_dispatch(target_id: str, content: str) -> None:
        calls.append((target_id, content))

    deny_msg = (
        "[lockout] You are a reader on /home/beryndil/Projects/Bearings. "
        "Run `/lockout claim-writer`."
    )
    script = _deny_script(exec_id, tool_name="Write", error=deny_msg)
    runner = SessionRunner(
        exec_id,
        ScriptedAgent(exec_id, scripts=[script]),
        db,
        prompt_dispatch=fake_dispatch,
    )
    await _run_one_turn(runner)

    assert len(calls) == 1, f"expected one BLOCKED dispatch, got {calls!r}"
    target, content = calls[0]
    assert target == orch_id
    assert content.startswith("BLOCKED — ")
    assert "Write" in content
    assert "reader" in content


@pytest.mark.asyncio
async def test_lockout_deny_with_no_orchestrator_skips_callback(
    db: aiosqlite.Connection,
) -> None:
    """Stand-alone executor (no `Orchestrator:` line in
    `session_instructions`) hits a lockout deny → no callback, no
    crash. Pins the no-regression contract for one-off bug sessions
    that aren't part of an orchestrator/audit pattern."""
    exec_id, _orch_id = await _ids(db)
    # Wipe the executor's instructions so no orchestrator can be
    # resolved. The orchestrator session row still exists in the DB
    # — that's fine; resolution is gated by the executor's own
    # instructions, not by the orchestrator's presence.
    await store.update_session(
        db, exec_id, fields={"session_instructions": "Some unrelated instructions"}
    )

    calls: list[tuple[str, str]] = []

    async def fake_dispatch(target_id: str, content: str) -> None:
        calls.append((target_id, content))

    script = _deny_script(
        exec_id,
        tool_name="Edit",
        error="[lockout] /home/beryndil/Projects/Foo is locked by writer session deadbeef.",
    )
    runner = SessionRunner(
        exec_id,
        ScriptedAgent(exec_id, scripts=[script]),
        db,
        prompt_dispatch=fake_dispatch,
    )
    await _run_one_turn(runner)

    assert calls == [], f"expected no callback for stand-alone executor, got {calls!r}"


@pytest.mark.asyncio
async def test_non_lockout_tool_failure_skips_callback(
    db: aiosqlite.Connection,
) -> None:
    """An ordinary tool failure (e.g. an Edit with mismatched
    `old_string`, returning `is_error=True` with a non-lockout
    message) must NOT trigger the callback. The sniffer keys on the
    `[lockout] ` prefix; anything else is left alone."""
    exec_id, _orch_id = await _ids(db)

    calls: list[tuple[str, str]] = []

    async def fake_dispatch(target_id: str, content: str) -> None:
        calls.append((target_id, content))

    script = _deny_script(
        exec_id,
        tool_name="Edit",
        error="String to replace not found in file.",
    )
    runner = SessionRunner(
        exec_id,
        ScriptedAgent(exec_id, scripts=[script]),
        db,
        prompt_dispatch=fake_dispatch,
    )
    await _run_one_turn(runner)

    assert calls == [], f"non-lockout error must not trigger callback: {calls!r}"


@pytest.mark.asyncio
async def test_lockout_deny_on_non_locked_tool_skips_callback(
    db: aiosqlite.Connection,
) -> None:
    """Defense-in-depth: even if the deny message starts with the
    lockout prefix, a tool outside `LOCKED_TOOLS` (e.g. `Bash`) must
    not fire the callback. The hook never denies non-write tools, so
    matching them would only inflate noise."""
    exec_id, _orch_id = await _ids(db)

    calls: list[tuple[str, str]] = []

    async def fake_dispatch(target_id: str, content: str) -> None:
        calls.append((target_id, content))

    script = _deny_script(
        exec_id,
        tool_name="Bash",
        error="[lockout] hypothetical future deny on Bash.",
    )
    runner = SessionRunner(
        exec_id,
        ScriptedAgent(exec_id, scripts=[script]),
        db,
        prompt_dispatch=fake_dispatch,
    )
    await _run_one_turn(runner)

    assert calls == [], f"non-locked tool must not trigger callback: {calls!r}"


@pytest.mark.asyncio
async def test_lockout_deny_with_no_dispatcher_does_not_crash(
    db: aiosqlite.Connection,
) -> None:
    """Runner constructed without `prompt_dispatch` (today's tests,
    legacy callers) hits a lockout deny → silent skip, turn completes
    cleanly. No log spam expected; the call site short-circuits before
    any DB lookup."""
    exec_id, _orch_id = await _ids(db)

    script = _deny_script(
        exec_id,
        tool_name="Write",
        error="[lockout] reader on /tmp.",
    )
    runner = SessionRunner(
        exec_id,
        ScriptedAgent(exec_id, scripts=[script]),
        db,
        # prompt_dispatch deliberately omitted.
    )
    # The assertion is "no crash" — `_run_one_turn` raising would fail.
    await _run_one_turn(runner)
