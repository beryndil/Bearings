"""Runner-fleet types crossing the ``agent`` ⇄ ``web`` boundary.

Item 1.1 lays the type surface; item 1.2 fills in the worker loop +
prompt queue + ring buffer + subscriber set per arch §1.1.4. Two
shapes land in this file now because every other module in the
``agent`` layer that needs to compose with the runner fleet (notably
:class:`bearings.agent.session.SessionConfig` consumers like
``agent/auto_driver.py``) has to import them at type-check time.

Both types are deliberately minimal: :class:`SessionRunner` is an
empty placeholder class so :class:`RunnerFactory`'s ``__call__``
return type resolves; :class:`RunnerStatus` is the frozen-dataclass
shape arch §4.11 names. Item 1.2 expands ``SessionRunner``'s body
(adds ``stream(prompt)``, ``interrupt()``, ``set_model(...)``, and the
worker-loop machinery) without changing the public class name.

The :class:`RunnerFactory` Protocol breaks the v0.17.x cycle that arch
§3.2 documents: in v0.17.x ``agent/auto_driver_runtime.py`` did a
function-local
``from bearings.api.ws_agent import build_runner`` to get past the
upper-layer reference; in v1 the binding is injected at app
construction by ``web/runner_factory.py``, and the ``agent`` layer
takes the Protocol as a constructor argument. The cycle-prevention
test in ``tests/test_session_runner_factory.py`` AST-walks every
``*.py`` under ``src/bearings/agent/`` and fails on any
``bearings.web.*`` or ``bearings.cli.*`` import.

References:

* ``docs/architecture-v1.md`` §3.1 (layer rules), §3.2 (cycle
  catalogue), §4.5 (``RunnerFactory`` Protocol shape), §4.11
  (``RunnerStatus`` shape).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bearings.agent.routing import RoutingDecision


class SessionRunner:
    """Placeholder — item 1.2 attaches the worker loop and queues.

    Item 1.1 declares the class so :class:`RunnerFactory`'s ``__call__``
    return type resolves at type-check and at runtime. Item 1.2 (the
    streaming-protocol item) adds:

    * a worker task that consumes a prompt queue;
    * a per-session ring buffer for WS replay;
    * a subscriber set + idle-reap signal;
    * forwarding methods (``stream``, ``interrupt``, ``set_model``,
      ``set_permission_mode``) that delegate to the wrapped
      :class:`bearings.agent.session.AgentSession`.

    Per arch §1.1.4 the runner is the one file in the ``agent``
    package allowed to exceed the §FileSize 400-line cap (≤450 lines).
    Item 1.1 leaves the body empty so the placeholder doesn't drift in
    advance of 1.2's design.
    """


@dataclass(frozen=True)
class RunnerStatus:
    """Arch §4.11 — frozen status snapshot for ``runner_status`` WS frames.

    The :data:`routing_decision` field is new in v1: v0.17.x's
    ``RunnerStatus`` had no routing surface, so the badge (spec §5)
    couldn't render on the first paint after a WS reconnect. Carrying
    the active decision here means the inspector can re-paint the
    badge before the next ``MessageComplete`` arrives.
    """

    is_running: bool
    is_awaiting_user: bool
    routing_decision: RoutingDecision | None


class RunnerFactory(Protocol):
    """Arch §4.5 — async factory that materialises a runner for ``session_id``.

    The concrete binding lives in ``web/runner_factory.py``
    (FastAPI-aware: reads ``app.state``); the ``agent`` layer takes
    this Protocol as a constructor argument so it never imports
    ``bearings.web``. Per arch §3.1 rule #4 there are no lazy
    cross-layer imports anywhere in the ``agent`` package; the cycle
    is broken by injection at app construction, not by deferred
    binding.
    """

    async def __call__(self, session_id: str) -> SessionRunner: ...


__all__ = ["RunnerFactory", "RunnerStatus", "SessionRunner"]
