"""Per-session runner that owns agent execution independently of any
WebSocket connection.

Why: in v0.2.x the agent loop lived inside the WS handler, so closing
the socket killed the in-flight stream. Sessions are meant to be
independent — kick off work in one and walk away. The runner owns the
`AgentSession`, the streaming task, and a ring buffer of recent events;
WS handlers become thin subscribers that can come and go without
disturbing execution. Completed messages/tool calls are persisted to
SQLite by `turn_executor.execute_turn`, so reconnecting after a server
restart also works.

Lifecycle: first WS connect constructs and registers a runner. It lives
until app shutdown or session deletion. Subscribers attach via
`subscribe(since_seq)` and replay any buffered events with seq >
since_seq. A single worker task drains the prompt queue.

Nothing here depends on FastAPI or WebSockets — that's deliberate so
the runner is trivially testable.

Module layout: this file owns `SessionRunner`. Worker loop and per-turn
execution live in `turn_executor.py`; wire types/tunables in
`runner_types.py`; subscribe/unsubscribe/should_reap in
`runner_subscribers.py`; tickers in `progress_ticker.py`; assistant-turn
persistence in `persist.py`; runner-level approval gate (counter +
broadcast on top of `ApprovalBroker`) in `runner_approval.py`;
Directory Context System markers in `runner_directory.py`. The
`runner_types` symbols and `_persist_assistant_turn` are re-exported
here for backwards compat.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

import aiosqlite
from claude_agent_sdk import ClaudeSDKError

from bearings.agent import runner_subscribers
from bearings.agent.approval_broker import ApprovalBroker
from bearings.agent.event_fanout import emit_ephemeral, emit_event
from bearings.agent.events import AgentEvent
from bearings.agent.progress_ticker import ProgressTickerManager
from bearings.agent.runner_approval import ApprovalGate
from bearings.agent.runner_directory import DirectoryLifecycle
from bearings.agent.runner_types import (
    _SHUTDOWN,
    RING_MAX,
    SUBSCRIBER_QUEUE_MAX,
    TOOL_PROGRESS_INTERVAL_S,
    RunnerStatus,
    _Envelope,
    _Replay,
    _Shutdown,
    _Submit,
)
from bearings.agent.session import AgentSession
from bearings.agent.sessions_broker import SessionsBroker
from bearings.agent.tool_output_coalescer import ToolOutputCoalescer
from bearings.config import ArtifactsCfg

# Cross-runner prompt dispatch: `(target_session_id, content) -> None`.
# Wired by `bearings.api.ws_agent.build_runner` to a closure that
# lazy-spawns a runner via the registry and calls `submit_prompt`,
# mirroring the in-process path of `POST /api/sessions/{id}/prompt`.
# Today's only consumer is `bearings.agent.tool_deny_callback`, which
# synthesizes a BLOCKED callback to an executor's orchestrator on a
# tool deny (lockout-hook prefix or SDK canonical rejection — audit
# items #519 + #520). Kept generic so future cross-runner messaging
# can ride the same hook.
PromptDispatch = Callable[[str, str], Awaitable[None]]

# Re-exported for backwards compatibility — tests, `ws_agent`, and
# downstream callers import these names from `bearings.agent.runner`.
__all__ = [
    "RING_MAX",
    "SUBSCRIBER_QUEUE_MAX",
    "TOOL_PROGRESS_INTERVAL_S",
    "PromptDispatch",
    "RunnerStatus",
    "SessionRunner",
    "_Envelope",
    "_Replay",
    "_SHUTDOWN",
    "_Shutdown",
    "_Submit",
]


class SessionRunner:
    """Owns one session's agent execution. Long-lived; decoupled from
    WebSocket connections so sessions keep running when the UI walks
    away."""

    def __init__(
        self,
        session_id: str,
        agent: AgentSession,
        db: aiosqlite.Connection,
        *,
        sessions_broker: SessionsBroker | None = None,
        artifacts_cfg: ArtifactsCfg | None = None,
        prompt_dispatch: PromptDispatch | None = None,
    ) -> None:
        self.session_id = session_id
        self.agent = agent
        self.db = db
        # Sessions pubsub (None ok — publish helpers no-op on None).
        self._sessions_broker = sessions_broker
        # Cross-runner prompt dispatcher (audit items #519 + #520).
        # None in unit tests that skip the full app wiring; production
        # `build_runner` always provides one. Consumed by
        # `tool_deny_callback` to wake an orchestrator when this
        # executor's tool call gets denied by the lockout hook OR by
        # the SDK's permission gate.
        self._prompt_dispatch = prompt_dispatch
        # Phase-1 File Display settings; consumed by `_artifacts.py`'s
        # auto-register hook. None disables auto-register cleanly.
        self._artifacts_cfg = artifacts_cfg
        self._prompts: asyncio.Queue[str | _Submit | _Replay | _Shutdown] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._subscribers: set[asyncio.Queue[_Envelope]] = set()
        self._event_log: deque[_Envelope] = deque(maxlen=RING_MAX)
        self._next_seq = 1
        self._status: RunnerStatus = "idle"
        # Stream loop checks between events and calls `agent.interrupt()`
        # to cancel an in-flight tool call. Cleared on turn entry so a
        # stale flag can't short-circuit the next prompt.
        self._stop_requested = False
        # Tool-use approval state. Broker owns pending Futures and
        # ApprovalRequest/ApprovalResolved emission; gate adds the
        # runner-axis counter + state broadcast on top. `mode_getter`
        # is a closure (not a stored value) so a mid-turn
        # `set_permission_mode` flip is observed on the very next
        # `can_use_tool` — without it a flip to bypassPermissions
        # wouldn't unstick a Future already parked under default mode
        # (root cause of the 2026-04-24 fae8f1a8 Settings-UX 4hr hang).
        self._approval = ApprovalBroker(
            session_id,
            self._emit_event,
            mode_getter=lambda: self.agent.permission_mode,
        )
        self._approval_gate = ApprovalGate(
            session_id,
            agent,
            db,
            self._approval,
            sessions_broker,
            is_running=lambda: self.is_running,
        )
        # Coalesces `ToolOutputDelta` → `append_tool_output` writes per
        # `tool_call_id`. Runner forwards buffer/drop/flush_all.
        self._coalescer = ToolOutputCoalescer(db, session_id)
        # Per-tool-call keepalive ticker manager. The lambda interval-
        # getter re-reads the module-level constant on each tick so
        # `monkeypatch.setattr(runner_mod, "TOOL_PROGRESS_INTERVAL_S", X)`
        # is observed on the very next sleep.
        self._progress = ProgressTickerManager(
            session_id,
            self._emit_ephemeral,
            lambda: TOOL_PROGRESS_INTERVAL_S,
        )
        # Monotonic timestamp of the most recent "quiet" transition
        # (idle AND zero subscribers). Reaper uses `now - _quiet_since`
        # vs. configured TTL. `None` = active on some axis. Initialized
        # at construction (no subscribers + idle); the ws handler flips
        # it off via `subscribe()` immediately, so the initial window
        # is effectively zero.
        self._quiet_since: float | None = time.monotonic()
        # Directory Context System (v0.6.1) lifecycle. Markers land
        # exactly once per runner lifetime regardless of WS reconnects.
        self._directory = DirectoryLifecycle(session_id, agent)

    # ---- backwards-compat ticker accessors ------------------------
    #
    # `test_runner_tool_progress.py` reads `runner._progress_tickers`
    # and `runner._progress_started` directly. Keep that surface as
    # property forwards onto the manager so the tests keep passing
    # without churn.

    @property
    def _progress_tickers(self) -> dict[str, asyncio.Task[None]]:
        return self._progress.tickers

    @property
    def _progress_started(self) -> dict[str, float]:
        return self._progress.started

    def _start_progress_ticker(self, tool_call_id: str) -> None:
        self._progress.start(tool_call_id)

    def _stop_progress_ticker(self, tool_call_id: str) -> None:
        self._progress.stop(tool_call_id)

    async def _stop_all_progress_tickers(self) -> None:
        await self._progress.stop_all()

    # ---- lifecycle -------------------------------------------------

    def start(self) -> None:
        """Spawn the worker task. Idempotent — safe to call twice."""
        if self._worker is None or self._worker.done():
            # Late import to break the runner ↔ turn_executor cycle.
            from bearings.agent.turn_executor import run_worker

            self._worker = asyncio.create_task(run_worker(self), name=f"runner:{self.session_id}")

    async def shutdown(self) -> None:
        """Drain the prompt queue and stop the worker. Used on app
        shutdown and on session deletion. If a turn is in flight, the
        SDK client is interrupted first so the subprocess winds down."""
        self._stop_requested = True
        # Deny any pending approvals with `interrupt=True` so the SDK
        # stops waiting for a user decision that will never come and
        # the stream loop can reach its shutdown path.
        await self._approval.deny_all("runner shutting down", interrupt=True)
        try:
            await self.agent.interrupt()
        except (ClaudeSDKError, OSError):
            # Best-effort — the worker's own exception handling will
            # log if the stream dies unexpectedly.
            pass
        await self._prompts.put(_SHUTDOWN)
        if self._worker is not None:
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
        # Directory Context System: append the matching end-marker.
        await self._directory.note_end()

    async def note_directory_context_start(self) -> None:
        """Idempotent one-shot. Stamps the `history.jsonl` start
        marker and kicks off stale-state revalidation in the
        background. Called by the WS handler after `registry.get_or_create`
        so the FS work runs at most once per runner-lifetime, not once
        per connection. See `runner_directory.DirectoryLifecycle` for
        the body."""
        await self._directory.note_start()

    # ---- public API ------------------------------------------------

    @property
    def status(self) -> RunnerStatus:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._status == "running"

    @property
    def is_awaiting_user(self) -> bool:
        """True iff parked inside `can_use_tool`, awaiting a user
        decision. Drives the sidebar's red-flashing indicator —
        distinct from `is_running`, which stays true across the whole
        turn including the park."""
        return self._approval_gate.is_awaiting_user

    async def submit_prompt(
        self,
        prompt: str,
        *,
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        """Queue a prompt for this session. Prompts are processed
        sequentially — if a turn is already in flight, this one waits.

        `attachments` is the sidecar list from the composer's
        `[File N]` tokens. None/empty queues a plain string (preserving
        the historical attachment-free queue shape); with attachments
        the prompt is wrapped in `_Submit` so the worker persists the
        sidecar and substitutes paths for the SDK.

        Refuses with an `ErrorEvent` if the session's `max_budget_usd`
        is set and `total_cost_usd` has met or exceeded it. The SDK's
        own advisory only fires during a turn once cost accrues, so
        without this pre-check a user past their cap could kick off
        another turn that runs to completion. Fail-closed at the gate.
        """
        from bearings.agent.events import ErrorEvent
        from bearings.db import store

        row = await store.get_session(self.db, self.session_id)
        if row is not None:
            cap = row.get("max_budget_usd")
            spent = row.get("total_cost_usd") or 0.0
            if cap is not None and float(spent) >= float(cap):
                await self._emit_event(
                    ErrorEvent(
                        session_id=self.session_id,
                        message=(
                            f"Budget cap reached: ${float(spent):.2f} of "
                            f"${float(cap):.2f}. Raise the cap in session "
                            "settings or fork to a new session to continue."
                        ),
                    )
                )
                return
        if attachments:
            await self._prompts.put(_Submit(prompt, attachments))
        else:
            await self._prompts.put(prompt)

    async def set_permission_mode(self, mode: Any) -> None:
        """Forwarder to `ApprovalGate.set_permission_mode`. See that
        method's docstring for the retro-apply rationale."""
        await self._approval_gate.set_permission_mode(mode)

    async def request_stop(self) -> None:
        """User-initiated stop of the current turn. Flags the worker
        loop and calls `agent.interrupt()` so the SDK aborts any
        in-flight tool call. Safe to call when idle (no-op)."""
        self._stop_requested = True
        # If the turn is parked on a pending approval, the stream won't
        # make any progress toward the stop flag until the Future is
        # resolved. Deny them all with `interrupt=True` so the SDK
        # unwinds and the loop reaches the stop check.
        await self._approval.deny_all("stopped by user", interrupt=True)
        try:
            await self.agent.interrupt()
        except (ClaudeSDKError, OSError):
            pass

    # ---- tool-use approval (delegates to ApprovalGate) -------------

    @property
    def can_use_tool(self) -> Any:
        """Bound onto `AgentSession.can_use_tool` by `ws_agent.build_runner`.
        Forwards to the gate's wrapped callback (counter + broadcast
        on top of the broker)."""
        return self._approval_gate.can_use_tool

    def _publish_runner_state(self) -> None:
        """Broadcast `(is_running, is_awaiting_user)` on the sessions
        broker. Kept on the runner because `turn_executor` calls it on
        turn-state transitions; thin forwarder to the gate."""
        self._approval_gate.publish_state()

    async def resolve_approval(
        self,
        request_id: str,
        decision: str,
        reason: str | None = None,
        updated_input: dict[str, object] | None = None,
    ) -> None:
        """WS → broker forwarder via the gate. Kept on the runner so
        the WS handler holds one object, not two."""
        await self._approval_gate.resolve_approval(request_id, decision, reason, updated_input)

    # ---- subscriber lifecycle (bodies in `runner_subscribers.py`) -

    async def subscribe(
        self, since_seq: int = 0
    ) -> tuple[asyncio.Queue[_Envelope], list[_Envelope]]:
        return await runner_subscribers.subscribe(self, since_seq)

    def unsubscribe(self, queue: asyncio.Queue[_Envelope]) -> None:
        runner_subscribers.unsubscribe(self, queue)

    def should_reap(self, now: float, ttl_seconds: float) -> bool:
        return runner_subscribers.should_reap(self, now, ttl_seconds)

    # ---- event fan-out --------------------------------------------
    #
    # Thin forwarders onto `event_fanout.emit_event` / `emit_ephemeral`.
    # Kept as methods (rather than swapping every `self._emit_event(...)`
    # call site to the free function) so the broker, ticker manager,
    # and turn executor can treat the runner as a callback target.

    async def _emit_event(self, event: AgentEvent) -> None:
        await emit_event(self, event)

    async def _emit_ephemeral(self, event: AgentEvent) -> None:
        await emit_ephemeral(self, event)


# Backwards-compat alias for tests that reach for
# `runner._persist_assistant_turn`. Active call sites moved to
# `bearings.agent.persist.persist_assistant_turn`.
from bearings.agent.persist import (  # noqa: E402, F401
    persist_assistant_turn as _persist_assistant_turn,
)
