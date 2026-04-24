"""Tests for the `ToolProgress` keepalive ticker.

Covers the silence-gap fix plan's P1 arm. A `ToolCallStart` spawns a
per-call ticker that fires `ToolProgress` events every
`TOOL_PROGRESS_INTERVAL_S` for fan-out only (no ring buffer append,
no DB write). The ticker is cancelled by the matching `ToolCallEnd`
and by turn-teardown paths (stop, exception) so an interrupted turn
doesn't strand timers.

To keep the suite fast, we monkeypatch `TOOL_PROGRESS_INTERVAL_S`
down to a few milliseconds — the timing-dependent paths still use
real `asyncio.sleep` so the invariants we pin (fan-out, not persisted,
cancelled correctly) are the real contract, just at a tighter cadence.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest

from bearings.agent import runner as runner_mod
from bearings.agent.events import (
    AgentEvent,
    MessageComplete,
    MessageStart,
    ToolCallEnd,
    ToolCallStart,
    ToolProgress,
)
from bearings.agent.runner import SessionRunner
from bearings.agent.session import AgentSession
from bearings.db import store
from bearings.db._common import init_db

# Slightly longer than anything the test needs to wait on; short enough
# the suite stays fast. 5ms lets us loop for 50ms and observe ~10 ticks
# worth of fan-out without flake.
FAST_INTERVAL_S = 0.005


class ScriptedAgent(AgentSession):
    """Minimal stub that yields a pre-programmed event list once.

    Lives in this file rather than a shared fixture so the coalesce
    tests keep their own simpler variant. None of the progress tests
    need the mid-turn gate machinery from `test_runner.py`."""

    def __init__(self, session_id: str, script: list[AgentEvent]) -> None:
        super().__init__(session_id, working_dir="/tmp", model="m")
        self._script = script

    async def stream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        for event in self._script:
            yield event

    async def interrupt(self) -> None:  # pragma: no cover - unused here
        pass


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    conn = await init_db(tmp_path / "progress.sqlite")
    await store.create_session(conn, working_dir="/tmp", model="m", title="t")
    yield conn
    await conn.close()


async def _session_id(conn: aiosqlite.Connection) -> str:
    rows = await store.list_sessions(conn)
    return rows[0]["id"]


def _make_runner(sid: str, db: aiosqlite.Connection, script: list[AgentEvent]) -> SessionRunner:
    return SessionRunner(sid, ScriptedAgent(sid, script), db)


async def _subscribe_and_collect(runner: SessionRunner, *, stop_event: asyncio.Event) -> list[dict]:
    """Attach a subscriber and return every event it sees until
    `stop_event` is set. Used to observe fan-out in real time."""
    queue, _ = await runner.subscribe(since_seq=0)
    seen: list[dict] = []
    try:
        while not stop_event.is_set():
            try:
                env = await asyncio.wait_for(queue.get(), timeout=0.05)
            except TimeoutError:
                continue
            seen.append(env.payload)
    finally:
        runner.unsubscribe(queue)
    return seen


# ---- ticker start/stop lifecycle -----------------------------------


@pytest.mark.asyncio
async def test_start_progress_ticker_is_idempotent(db: aiosqlite.Connection) -> None:
    """A duplicate `ToolCallStart` for the same id (which the reducer
    also treats as a no-op) keeps the original ticker rather than
    leaking a second task. If this regresses, a buggy stream that
    re-announces a call would grow unbounded tickers."""
    sid = await _session_id(db)
    runner = _make_runner(sid, db, script=[])

    runner._start_progress_ticker("tc-1")
    first = runner._progress_tickers["tc-1"]
    runner._start_progress_ticker("tc-1")
    second = runner._progress_tickers["tc-1"]

    assert first is second, "duplicate start should not replace the task"
    runner._stop_progress_ticker("tc-1")
    await asyncio.sleep(0)  # let the cancel resolve
    assert "tc-1" not in runner._progress_tickers


@pytest.mark.asyncio
async def test_stop_progress_ticker_no_op_on_unknown_id(db: aiosqlite.Connection) -> None:
    """Safe to stop an id that was never started (or already stopped).
    The turn loop pairs start/stop naturally, but the defensive contract
    matters for stop/exception paths that re-enter via
    `_stop_all_progress_tickers`."""
    sid = await _session_id(db)
    runner = _make_runner(sid, db, script=[])
    runner._stop_progress_ticker("nonexistent")  # must not raise


@pytest.mark.asyncio
async def test_stop_all_progress_tickers_cancels_outstanding(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every in-flight ticker gets cancelled and awaited so the turn's
    finally block can exit cleanly."""
    monkeypatch.setattr(runner_mod, "TOOL_PROGRESS_INTERVAL_S", FAST_INTERVAL_S)
    sid = await _session_id(db)
    runner = _make_runner(sid, db, script=[])

    runner._start_progress_ticker("tc-a")
    runner._start_progress_ticker("tc-b")
    assert len(runner._progress_tickers) == 2

    await runner._stop_all_progress_tickers()
    assert runner._progress_tickers == {}
    assert runner._progress_started == {}


# ---- ticker fan-out -------------------------------------------------


@pytest.mark.asyncio
async def test_ticker_fires_tool_progress_events(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A started ticker emits `ToolProgress` events to subscribers
    at the configured cadence. Verifies the event type + session/
    tool ids round-trip through the fan-out path."""
    monkeypatch.setattr(runner_mod, "TOOL_PROGRESS_INTERVAL_S", FAST_INTERVAL_S)
    sid = await _session_id(db)
    runner = _make_runner(sid, db, script=[])

    stop = asyncio.Event()
    collector = asyncio.create_task(_subscribe_and_collect(runner, stop_event=stop))

    runner._start_progress_ticker("tc-fan")
    # Let several ticks land. 50ms at 5ms cadence → ~10 emits; we
    # assert on a lower bound to avoid flake from loop scheduling.
    await asyncio.sleep(0.05)
    runner._stop_progress_ticker("tc-fan")
    stop.set()
    seen = await collector

    progress = [p for p in seen if p["type"] == "tool_progress"]
    assert len(progress) >= 3, f"expected multiple ticks, got {len(progress)}"
    assert all(p["session_id"] == sid for p in progress)
    assert all(p["tool_call_id"] == "tc-fan" for p in progress)
    # elapsed_ms monotonically grows across ticks.
    elapsed = [p["elapsed_ms"] for p in progress]
    assert elapsed == sorted(elapsed), f"elapsed_ms not monotonic: {elapsed}"


@pytest.mark.asyncio
async def test_tool_progress_is_ephemeral_not_in_ring_buffer(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ToolProgress` must NOT land in the ring buffer. A reconnecting
    client should pull cumulative tool output + the next live tick,
    not hundreds of stale keepalive ticks. This pin guards the
    `_emit_ephemeral` path from a future refactor that conflates it
    with `_emit_event`."""
    monkeypatch.setattr(runner_mod, "TOOL_PROGRESS_INTERVAL_S", FAST_INTERVAL_S)
    sid = await _session_id(db)
    runner = _make_runner(sid, db, script=[])

    # Drive a few ticks directly without a subscriber — simplest way
    # to observe the ring-buffer side of the contract.
    runner._start_progress_ticker("tc-eph")
    await asyncio.sleep(0.03)
    runner._stop_progress_ticker("tc-eph")
    await asyncio.sleep(FAST_INTERVAL_S * 2)  # let any in-flight emit settle

    # The ring buffer should contain zero tool_progress envelopes.
    types = [env.payload.get("type") for env in runner._event_log]
    assert "tool_progress" not in types, f"ring buffer leaked: {types}"

    # A fresh subscriber with since_seq=0 gets no replay of the ticks.
    queue, replay = await runner.subscribe(since_seq=0)
    assert all(env.payload.get("type") != "tool_progress" for env in replay)
    runner.unsubscribe(queue)


@pytest.mark.asyncio
async def test_ticker_stops_without_subscribers(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ticker keeps firing even with zero subscribers; the emit
    simply fans out to nobody. Guards against a future optimization
    that gates the ticker on subscriber count — we deliberately keep
    firing so that a mid-sub-agent reconnect immediately lands on a
    warm wire."""
    monkeypatch.setattr(runner_mod, "TOOL_PROGRESS_INTERVAL_S", FAST_INTERVAL_S)
    sid = await _session_id(db)
    runner = _make_runner(sid, db, script=[])

    seq_before = runner._next_seq
    runner._start_progress_ticker("tc-solo")
    await asyncio.sleep(0.03)
    runner._stop_progress_ticker("tc-solo")
    await asyncio.sleep(FAST_INTERVAL_S * 2)

    # Seq advanced — ephemeral emits still consume sequence numbers.
    assert runner._next_seq > seq_before


# ---- turn-loop integration -----------------------------------------


@pytest.mark.asyncio
async def test_turn_loop_starts_and_stops_ticker_around_tool_call(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running a full scripted turn spawns a ticker on `ToolCallStart`
    and tears it down on `ToolCallEnd`. After the turn exits,
    `_progress_tickers` is empty — the silence-gap fix can't leave
    timers behind or subsequent turns inherit stale state."""
    monkeypatch.setattr(runner_mod, "TOOL_PROGRESS_INTERVAL_S", FAST_INTERVAL_S)
    sid = await _session_id(db)
    script: list[AgentEvent] = [
        MessageStart(session_id=sid, message_id="m-1"),
        ToolCallStart(
            session_id=sid, tool_call_id="tc-turn", name="Agent", input={"description": "x"}
        ),
        ToolCallEnd(session_id=sid, tool_call_id="tc-turn", ok=True, output="done", error=None),
        MessageComplete(session_id=sid, message_id="m-1", cost_usd=None),
    ]
    runner = _make_runner(sid, db, script=script)

    runner.start()
    await runner.submit_prompt("go")
    for _ in range(400):
        await asyncio.sleep(0.01)
        if not runner.is_running:
            break
    else:  # pragma: no cover - safety net
        raise AssertionError("turn did not complete within timeout")

    assert runner._progress_tickers == {}
    assert runner._progress_started == {}
    await runner.shutdown()


@pytest.mark.asyncio
async def test_turn_teardown_cancels_tickers_on_exception(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the stream loop explodes after a `ToolCallStart` but before
    the matching `ToolCallEnd`, the `finally` block must still
    cancel every outstanding ticker. Regression would manifest as
    `ToolProgress` events continuing to fire on a subscriber after
    its parent turn errored out."""
    monkeypatch.setattr(runner_mod, "TOOL_PROGRESS_INTERVAL_S", FAST_INTERVAL_S)
    sid = await _session_id(db)

    class Boom(Exception):
        pass

    class ExplodingAgent(AgentSession):
        def __init__(self) -> None:
            super().__init__(sid, working_dir="/tmp", model="m")

        async def stream(self, prompt: str) -> AsyncIterator[AgentEvent]:
            yield MessageStart(session_id=sid, message_id="m-1")
            yield ToolCallStart(session_id=sid, tool_call_id="tc-boom", name="Agent", input={})
            raise Boom("kaboom")

        async def interrupt(self) -> None:  # pragma: no cover
            pass

    runner = SessionRunner(sid, ExplodingAgent(), db)
    runner.start()
    await runner.submit_prompt("go")
    for _ in range(400):
        await asyncio.sleep(0.01)
        if not runner.is_running:
            break
    else:  # pragma: no cover
        raise AssertionError("turn did not complete within timeout")

    assert runner._progress_tickers == {}
    await runner.shutdown()


# ---- schema ---------------------------------------------------------


def test_tool_progress_event_shape() -> None:
    """Pydantic serialisation produces the exact wire shape the
    frontend reducer expects. Pinned here so a field rename on
    either side breaks a test before it breaks the UI."""
    ev = ToolProgress(session_id="s-1", tool_call_id="tc-1", elapsed_ms=12345)
    payload = ev.model_dump()
    assert payload == {
        "type": "tool_progress",
        "session_id": "s-1",
        "tool_call_id": "tc-1",
        "elapsed_ms": 12345,
    }
