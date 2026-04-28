"""FastAPI app factory.

Per ``docs/architecture-v1.md`` §1.1.5 ``web/app.py`` is the
``create_app(...) -> FastAPI`` factory wiring lifespan + every route
module + the static-bundle mount. Item 1.2 laid the streaming-only
WebSocket surface; item 1.4 adds the tags + memories REST routes.
Future items (1.5+) extend with sessions / messages / checklists /
templates routes; the factory's signature stays additive.

Connection wiring
-----------------

The tags + memories route modules read a long-lived
:class:`aiosqlite.Connection` off ``app.state.db_connection``. Tests
inject a freshly-bootstrapped connection directly; production callers
(item 1.5+ ``cli/serve.py``) attach via FastAPI's lifespan event so
the connection lives for the app's lifetime and is closed at shutdown.
The factory accepts the connection as an optional argument so the
existing streaming-only test surface keeps working unchanged.

References:

* ``docs/architecture-v1.md`` §1.1.5 — web layer responsibilities.
* ``docs/behavior/tool-output-streaming.md`` — observable WS
  subscriber lifecycle.
"""

from __future__ import annotations

import aiosqlite
from fastapi import FastAPI, WebSocket

from bearings.agent.auto_driver_runtime import AutoDriverRegistry, build_registry
from bearings.agent.runner import RunnerFactory
from bearings.config.constants import STREAM_HEARTBEAT_INTERVAL_S
from bearings.config.settings import VaultCfg
from bearings.web.routes.checklists import router as checklists_router
from bearings.web.routes.memories import router as memories_router
from bearings.web.routes.tags import router as tags_router
from bearings.web.routes.vault import router as vault_router
from bearings.web.runner_factory import build_in_process_factory
from bearings.web.streaming import SINCE_SEQ_QUERY_PARAM, serve_session_stream


def create_app(
    *,
    runner_factory: RunnerFactory | None = None,
    heartbeat_interval_s: float = STREAM_HEARTBEAT_INTERVAL_S,
    db_connection: aiosqlite.Connection | None = None,
    vault_cfg: VaultCfg | None = None,
    auto_driver_registry: AutoDriverRegistry | None = None,
) -> FastAPI:
    """Construct the FastAPI app.

    ``runner_factory`` defaults to a fresh in-process registry so each
    app has its own runner fleet — important for parallel test runs
    that must not share runner state.

    ``heartbeat_interval_s`` is exposed for tests that want a short
    interval; production callers should leave the default.

    ``db_connection`` enables the tags + memories + vault REST routes.
    If ``None`` the routers are still mounted but every handler
    returns 503 (per :func:`bearings.web.routes.tags._db`); this
    matches the streaming-only contract item 1.2 ships under.

    ``vault_cfg`` is the :class:`VaultCfg` the vault routes scan with.
    Defaults to a fresh ``VaultCfg()`` (which points at
    ``~/.claude/plans`` + ``~/Projects/**/TODO.md``); tests inject a
    cfg whose roots / globs target a ``tmp_path`` so the vault
    surface is deterministic.

    ``auto_driver_registry`` is the live-driver registry the
    checklist run-control routes (item 1.6) dispatch
    stop / skip-current signals through. Defaults to a fresh
    :class:`AutoDriverRegistry` so each app has its own driver fleet
    (important for parallel test runs that must not share state).
    """
    if heartbeat_interval_s <= 0:
        raise ValueError(f"heartbeat_interval_s must be > 0 (got {heartbeat_interval_s})")
    factory: RunnerFactory = runner_factory or build_in_process_factory()
    app = FastAPI()
    app.state.runner_factory = factory
    app.state.heartbeat_interval_s = heartbeat_interval_s
    app.state.db_connection = db_connection
    app.state.vault_cfg = vault_cfg if vault_cfg is not None else VaultCfg()
    app.state.auto_driver_registry = (
        auto_driver_registry if auto_driver_registry is not None else build_registry()
    )

    @app.websocket("/ws/sessions/{session_id}")
    async def stream_endpoint(websocket: WebSocket, session_id: str) -> None:
        # Resume cursor — defaults to 0 (replay everything still in
        # ring buffer) per behavior doc §"Reconnect / replay". The
        # query parameter name is the constant from the streaming
        # module so a rename there fails type-check here.
        raw = websocket.query_params.get(SINCE_SEQ_QUERY_PARAM, "0")
        try:
            since_seq = int(raw)
        except ValueError:
            await websocket.close(code=1003, reason="invalid since_seq")
            return
        runner = await factory(session_id)
        await serve_session_stream(
            websocket,
            runner,
            since_seq=since_seq,
            heartbeat_interval_s=heartbeat_interval_s,
        )

    app.include_router(tags_router)
    app.include_router(memories_router)
    app.include_router(vault_router)
    app.include_router(checklists_router)
    return app


__all__ = ["create_app"]
