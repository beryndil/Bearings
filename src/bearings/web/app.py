"""Minimal FastAPI app factory for item 1.2.

Per ``docs/architecture-v1.md`` §1.1.5 ``web/app.py`` is the
``create_app(settings) -> FastAPI`` factory wiring lifespan + every
route module + the static-bundle mount. Item 1.2 (this item) lays the
**streaming-only** version — just the per-session WebSocket handler
mounted at ``/ws/sessions/{session_id}``. REST routes / settings
loading / lifespan / static mount land in items 1.4+.

The factory accepts an optional :class:`RunnerFactory` so tests can
inject a fake runner; production callers (item 1.3+ ``cli/serve.py``)
will pass an :class:`bearings.web.runner_factory.InProcessRunnerRegistry`
constructed from the FastAPI ``app.state``.

References:

* ``docs/architecture-v1.md`` §1.1.5 — web layer responsibilities.
* ``docs/behavior/tool-output-streaming.md`` — observable
  WS subscriber lifecycle.
"""

from __future__ import annotations

from fastapi import FastAPI, WebSocket

from bearings.agent.runner import RunnerFactory
from bearings.config.constants import STREAM_HEARTBEAT_INTERVAL_S
from bearings.web.runner_factory import build_in_process_factory
from bearings.web.streaming import SINCE_SEQ_QUERY_PARAM, serve_session_stream


def create_app(
    *,
    runner_factory: RunnerFactory | None = None,
    heartbeat_interval_s: float = STREAM_HEARTBEAT_INTERVAL_S,
) -> FastAPI:
    """Construct the streaming-only FastAPI app.

    ``runner_factory`` defaults to a fresh in-process registry so
    each app has its own runner fleet — important for parallel test
    runs that must not share runner state.

    ``heartbeat_interval_s`` is exposed for tests that want a short
    interval; production callers should leave the default.
    """
    if heartbeat_interval_s <= 0:
        raise ValueError(f"heartbeat_interval_s must be > 0 (got {heartbeat_interval_s})")
    factory: RunnerFactory = runner_factory or build_in_process_factory()
    app = FastAPI()
    app.state.runner_factory = factory
    app.state.heartbeat_interval_s = heartbeat_interval_s

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

    return app


__all__ = ["create_app"]
