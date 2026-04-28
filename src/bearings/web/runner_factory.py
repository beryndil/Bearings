"""Concrete :class:`RunnerFactory` binding — FastAPI-aware.

Per ``docs/architecture-v1.md`` §1.1.5 and §3.2 (cycle catalogue),
this module is the **rebuild's solution** to v0.17.x's lazy-import
cycle ``agent/auto_driver_runtime.py → api.ws_agent.build_runner``.
The factory lives here, in the ``web`` layer; the
:class:`bearings.agent.runner.RunnerFactory` Protocol lets the
``agent`` layer accept the binding by injection without ever
importing :mod:`bearings.web`.

Item 1.2 lays an in-process registry keyed by ``session_id``: the
first call materialises a new :class:`SessionRunner`; subsequent
calls return the same instance. This is the runner reuse the
behavior doc relies on for ``since_seq`` replay across reconnects —
the ring buffer survives WS closes because the runner is sticky.

Idle-reap is deferred to item 1.3+ (the SDK-subprocess lifecycle
management surface). The registry's :meth:`InProcessRunnerRegistry.close_all`
exists for test-suite teardown; production code never calls it.

References:

* ``docs/architecture-v1.md`` §1.1.5 — ``web/runner_factory.py``.
* ``docs/architecture-v1.md`` §3.1 / §3.2 — layer rules + cycle break.
* ``docs/architecture-v1.md`` §4.5 — :class:`RunnerFactory` Protocol.
"""

from __future__ import annotations

from bearings.agent.runner import RunnerFactory, SessionRunner


class InProcessRunnerRegistry:
    """In-process ``session_id`` → :class:`SessionRunner` registry.

    Implements the :class:`bearings.agent.runner.RunnerFactory`
    Protocol structurally — the async ``__call__`` returns a sticky
    runner per session id. Sticky runners are what behavior doc
    §"Reconnect / replay" assumes: the ring buffer lives on the
    runner, so the runner has to outlive the WS connection.

    This class is **not** the per-WS-session SDK wrapper (that's
    :class:`bearings.agent.session.AgentSession`); it is the *runner
    registry* that the WS layer asks for a runner against a session
    id and gets a long-lived per-session worker back.
    """

    def __init__(self) -> None:
        self._runners: dict[str, SessionRunner] = {}

    async def __call__(self, session_id: str) -> SessionRunner:
        """Return the sticky runner for ``session_id``, creating one
        on first call. Async to satisfy the
        :class:`RunnerFactory` Protocol; the body is currently
        synchronous, but item 1.3+ extends with SDK-subprocess spawn
        which IS async.
        """
        if not session_id:
            raise ValueError("runner-factory session_id must be non-empty")
        runner = self._runners.get(session_id)
        if runner is None:
            runner = SessionRunner(session_id)
            self._runners[session_id] = runner
        return runner

    def get(self, session_id: str) -> SessionRunner | None:
        """Return the runner for ``session_id`` if registered, else
        ``None``. Synchronous accessor for tests / introspection
        (``__call__`` is async to satisfy the Protocol)."""
        return self._runners.get(session_id)

    def close_all(self) -> None:
        """Drop every registered runner. For test teardown only."""
        self._runners.clear()


def build_in_process_factory() -> RunnerFactory:
    """Construct a fresh :class:`InProcessRunnerRegistry` typed at
    the :class:`RunnerFactory` Protocol so call sites pass it through
    parameters typed against the Protocol.

    Equivalent to ``InProcessRunnerRegistry()`` but the explicit
    return-type annotation forces mypy to verify the structural
    typing — if the registry's ``__call__`` signature drifts from
    the Protocol the project fails type-check at this function
    rather than at the consumer.
    """
    return InProcessRunnerRegistry()


__all__ = ["InProcessRunnerRegistry", "build_in_process_factory"]
