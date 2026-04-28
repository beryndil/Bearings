"""HTTP / WebSocket surface for the Bearings v1 backend.

Per ``docs/architecture-v1.md`` §1.1.5 + §3.1, this is the **web**
layer: FastAPI app construction, route groups, WebSocket handlers, the
static-bundle mount. The package is renamed from v0.17.x's ``api/`` so
the import-graph rule reads naturally — ``cli > web > agent > db``.

Item 1.2 (this item) lays down:

* :mod:`bearings.web.serialize` — :class:`bearings.agent.events.AgentEvent`
  → JSON wire-frame round-tripping.
* :mod:`bearings.web.streaming` — per-session WebSocket handler
  (``/ws/sessions/{id}``) with ``since_seq`` replay + heartbeat.
* :mod:`bearings.web.runner_factory` — concrete :class:`RunnerFactory`
  binding (FastAPI-aware) that breaks the v0.17.x lazy-import cycle
  per arch §3.2.
* :mod:`bearings.web.app` — minimal :func:`create_app` factory that
  wires the WS route. Item 1.4+ extends with REST routes / lifespan /
  static mount.

The package's public surface is intentionally narrow at this stage —
each downstream item adds its own route module and re-exports the
router list. ``__all__`` here lists only the primitives the test
suite needs.
"""

from __future__ import annotations

__all__: list[str] = []
