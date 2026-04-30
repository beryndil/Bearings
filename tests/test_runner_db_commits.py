"""Per-turn DB commit-count regression test.

Pre-2026-04-30 a tool-heavy turn produced ~35 SQLite commits (one per
ToolCallStart, per coalesced ToolOutputDelta flush, per ToolCallEnd,
per ContextUsage, plus the four-write batched persist at the end). The
streaming functions now accept `commit=False` and `turn_executor`
defers every per-event write into the per-turn `persist_assistant_turn`
commit at MessageComplete time.

This test wraps the connection's `commit()` to count calls during a
scripted multi-tool turn and asserts the count drops to a handful.
The bound is loose (≤4) so unrelated hardening — e.g. an extra commit
on user-message insert, which we keep eager for orphan-replay safety
— doesn't trip it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest

from bearings.agent.events import (
    AgentEvent,
    ContextUsage,
    MessageComplete,
    MessageStart,
    ToolCallEnd,
    ToolCallStart,
    ToolOutputDelta,
)
from bearings.agent.runner import SessionRunner
from bearings.agent.session import AgentSession
from bearings.db import store
from bearings.db._common import init_db


class ScriptedAgent(AgentSession):
    """Yields a fixed event list. No gate, no interrupt — this test
    runs the script straight through and inspects DB side effects."""

    def __init__(self, session_id: str, script: list[AgentEvent]) -> None:
        super().__init__(session_id, working_dir="/tmp", model="m")
        self._script = script

    async def stream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        for event in self._script:
            yield event

    async def interrupt(self) -> None:
        return None


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    conn = await init_db(tmp_path / "commits.sqlite")
    await store.create_session(conn, working_dir="/tmp", model="m", title="t")
    yield conn
    await conn.close()


def _tool_heavy_script(sid: str, msg_id: str, n_tools: int = 8) -> list[AgentEvent]:
    """Build a turn that exercises every per-event write path:
    n_tools × (start + 5 deltas + end), plus a couple of ContextUsage
    snapshots, then MessageComplete."""
    events: list[AgentEvent] = [MessageStart(session_id=sid, message_id=msg_id)]
    for i in range(n_tools):
        tcid = f"tc-{i}"
        events.append(
            ToolCallStart(session_id=sid, tool_call_id=tcid, name="bash", input={"cmd": "ls"})
        )
        for j in range(5):
            events.append(ToolOutputDelta(session_id=sid, tool_call_id=tcid, delta=f"chunk-{j}\n"))
        events.append(
            ToolCallEnd(
                session_id=sid,
                tool_call_id=tcid,
                output=f"final-{i}",
                error=None,
                ok=True,
            )
        )
    events.append(
        ContextUsage(
            session_id=sid,
            model="m",
            percentage=12.5,
            total_tokens=12500,
            max_tokens=100000,
            is_auto_compact_enabled=True,
        )
    )
    events.append(MessageComplete(session_id=sid, message_id=msg_id, cost_usd=None))
    return events


async def test_per_turn_commits_stay_small(db: aiosqlite.Connection) -> None:
    """A turn with 8 tool calls × 5 output deltas + 1 context-usage +
    persist used to commit ~35 times. With deferred commits it should
    stay under a handful — proving the per-event commits are now
    folded into the per-turn batch."""
    sid = (await store.list_sessions(db))[0]["id"]
    agent = ScriptedAgent(sid, _tool_heavy_script(sid, "msg-perf", n_tools=8))
    runner = SessionRunner(sid, agent, db)

    commits = 0
    real_commit = db.commit

    async def counting_commit() -> None:
        nonlocal commits
        commits += 1
        await real_commit()

    db.commit = counting_commit  # type: ignore[method-assign]
    try:
        runner.start()
        await runner.submit_prompt("hi")
        # Wait for the turn to drain. The script ends in MessageComplete
        # which marks the turn persisted; subsequent get() blocks on an
        # empty queue. Poll the persisted message count instead of racing
        # against any specific timer.
        for _ in range(200):
            msgs = await store.list_messages(db, sid, limit=10)
            if any(m["role"] == "assistant" for m in msgs):
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("assistant turn never persisted")
    finally:
        db.commit = real_commit  # type: ignore[method-assign]
        await runner.shutdown()

    # The per-turn persist itself does ONE commit (`persist_assistant_turn`).
    # The user-message insert at turn entry does ONE more (kept eager
    # for orphan-replay safety). The `_mark_turn_starting` `touch_session`
    # adds another. Anything beyond a handful would mean the per-event
    # `commit=False` plumbing leaked. Cap at 4 to leave room for that
    # baseline plus one for unanticipated bookkeeping.
    assert commits <= 4, (
        f"expected ≤4 commits per turn, got {commits} — deferred-commit "
        f"plumbing likely regressed; check turn_executor + coalescer."
    )

    # Sanity: the assistant message + every tool_call landed.
    msgs = await store.list_messages(db, sid, limit=10)
    assert any(m["role"] == "assistant" for m in msgs)
    rows = await db.execute_fetchall("SELECT COUNT(*) FROM tool_calls WHERE session_id = ?", (sid,))
    assert rows[0][0] == 8


async def test_streaming_helpers_skip_commit_when_deferred(db: aiosqlite.Connection) -> None:
    """Direct contract test: each helper must skip `await conn.commit()`
    when called with `commit=False`. Wraps the connection commit so
    the assertion is unambiguous."""
    sid = (await store.list_sessions(db))[0]["id"]

    commits = 0
    real_commit = db.commit

    async def counting_commit() -> None:
        nonlocal commits
        commits += 1
        await real_commit()

    db.commit = counting_commit  # type: ignore[method-assign]
    try:
        await store.insert_tool_call_start(
            db,
            session_id=sid,
            tool_call_id="t-defer",
            name="bash",
            input_json="{}",
            commit=False,
        )
        await store.append_tool_output(db, tool_call_id="t-defer", chunk="x", commit=False)
        await store.finish_tool_call(
            db, tool_call_id="t-defer", output="done", error=None, commit=False
        )
        await store.set_session_context_usage(
            db, sid, pct=10.0, tokens=100, max_tokens=1000, commit=False
        )
        assert commits == 0, "deferred helpers must not commit"

        # Land everything explicitly so the rows are visible after
        # the test (otherwise the open transaction rolls back).
        await db.commit()
        assert commits == 1
    finally:
        db.commit = real_commit  # type: ignore[method-assign]

    # Sanity: the tool_call row exists with the canonical final output.
    row = await store.get_tool_call(db, "t-defer")
    assert row is not None
    assert row["output"] == "done"
