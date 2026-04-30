"""Runner-level approval gate. Sits on top of `ApprovalBroker` to add
the runner-axis state the broker shouldn't know about.

Responsibilities:

- Counter (`awaiting_count`) of in-flight `can_use_tool` parks. The
  SDK can stack a tool-approval and an `AskUserQuestion` in the same
  turn; both keep the sidebar's red-flashing "needs attention"
  indicator lit until every park resolves. A bool can't express that;
  a counter can.
- `runner_state` broadcast on the sessions broker every time the
  counter changes so subscribed UI tabs mirror the indicator.
- Permission-mode flips that retro-apply to parked Futures and
  persist to `sessions.permission_mode` (migration 0012). Forwarded
  through the gate so callers hold one object, not two.

The broker stays SDK-facing (pending Futures, request_id management).
The gate stays runner-facing (counter, broadcast, mode flip
persistence). This split keeps `ApprovalBroker` transport-agnostic
and reusable outside the runner.

Extracted from `runner.py` 2026-04-30 to keep the runner under the
project's 400-line cap. Public behavior unchanged — `SessionRunner`
delegates `can_use_tool`, `_publish_runner_state`, `resolve_approval`,
and `set_permission_mode` here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import aiosqlite

from bearings.agent.approval_broker import ApprovalBroker
from bearings.agent.session import AgentSession
from bearings.agent.sessions_broker import SessionsBroker, publish_runner_state
from bearings.db import store

log = logging.getLogger(__name__)


class ApprovalGate:
    """Wraps an `ApprovalBroker` with the runner-axis counter +
    `runner_state` broadcast that the broker itself shouldn't own."""

    def __init__(
        self,
        session_id: str,
        agent: AgentSession,
        db: aiosqlite.Connection,
        broker: ApprovalBroker,
        sessions_broker: SessionsBroker | None,
        is_running: Callable[[], bool],
    ) -> None:
        self._session_id = session_id
        self._agent = agent
        self._db = db
        self._broker = broker
        self._sessions_broker = sessions_broker
        # Closure (not stored bool) so the broadcast always reflects
        # the runner's current `is_running` even when this gate's
        # counter changes asynchronously relative to turn lifecycle.
        self._is_running = is_running
        # Counter (not bool) because the SDK can stack parks (tool
        # approval immediately followed by AskUserQuestion); both keep
        # the indicator lit until all resolve.
        self._awaiting_count: int = 0

    @property
    def awaiting_count(self) -> int:
        return self._awaiting_count

    @property
    def is_awaiting_user(self) -> bool:
        """True iff parked inside `can_use_tool`, awaiting a user
        decision. Covers both native tool-use approval and the
        AskUserQuestion flow (both ride the broker through the wrapped
        callback)."""
        return self._awaiting_count > 0

    @property
    def can_use_tool(self) -> Any:
        """Callback bound onto `AgentSession.can_use_tool`. Wraps the
        broker's callback so each entry/exit broadcasts a `runner_state`
        frame — the sidebar reads `awaiting_user` off that frame and
        flips the red-flashing "needs attention" indicator."""
        broker_cb = self._broker.can_use_tool

        async def wrapped(tool_name: Any, tool_input: Any, context: Any) -> Any:
            self._awaiting_count += 1
            self.publish_state()
            try:
                return await broker_cb(tool_name, tool_input, context)
            finally:
                # Decrement THEN broadcast so the published frame
                # reflects the post-resolve count. A stacked approval
                # + AskUserQuestion keeps the indicator lit until the
                # last one resolves — the counter's whole point.
                self._awaiting_count -= 1
                self.publish_state()

        return wrapped

    def publish_state(self) -> None:
        """Broadcast `(is_running, is_awaiting_user)` on the sessions
        broker. No-op when no broker is wired (test runners). Idempotent
        — a frame identical to the last one is harmless; subscribers
        just re-apply the same state."""
        publish_runner_state(
            self._sessions_broker,
            self._session_id,
            is_running=self._is_running(),
            is_awaiting_user=self.is_awaiting_user,
        )

    async def resolve_approval(
        self,
        request_id: str,
        decision: str,
        reason: str | None = None,
        updated_input: dict[str, object] | None = None,
    ) -> None:
        """WS → broker forwarder. `updated_input` is the UI-collected
        override the SDK passes to the tool on allow — see
        `ApprovalBroker.resolve` for the AskUserQuestion motivation."""
        await self._broker.resolve(request_id, decision, reason, updated_input)

    async def set_permission_mode(self, mode: Any) -> None:
        """Update the SDK's permission mode AND retro-apply it to any
        approval already parked. Forwarding to the SDK alone isn't
        enough — the SDK only consults the new mode on the *next*
        `can_use_tool`, so a flip to bypassPermissions while a modal
        is on screen would still strand the user. The broker clears
        parked Futures per the accept-edits/bypass matrix and emits
        `approval_resolved` so mirroring tabs drop their modals too.

        Persists to `sessions.permission_mode` (migration 0012) so a
        browser reload or socket drop restores the same mode."""
        self._agent.set_permission_mode(mode)
        if isinstance(mode, str):
            await self._broker.resolve_for_mode(mode)
        # Persist str modes and explicit None (== clear the override).
        # Non-string truthy values are treated as malformed wire frames
        # and left alone — don't clobber a good DB value with a bad
        # one. Invalid strings are rejected by the store helper; we
        # swallow that ValueError so a bad frame can't crash the runner.
        if isinstance(mode, str) or mode is None:
            try:
                await store.set_session_permission_mode(self._db, self._session_id, mode)
            except ValueError:
                log.warning(
                    "runner %s: rejected unknown permission mode %r",
                    self._session_id,
                    mode,
                )
