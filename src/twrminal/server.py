from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from twrminal import __version__
from twrminal.api import routes_health, routes_history, routes_metrics, routes_sessions, ws_agent
from twrminal.config import Settings, load_settings

STATIC_DIR = Path(__file__).parent / "web" / "dist"


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or load_settings()
    app = FastAPI(title="Twrminal", version=__version__)
    app.state.settings = cfg

    app.include_router(routes_health.router, prefix="/api")
    app.include_router(routes_sessions.router, prefix="/api")
    app.include_router(routes_history.router, prefix="/api")
    app.include_router(routes_metrics.router)
    app.include_router(ws_agent.router)

    if STATIC_DIR.exists() and any(STATIC_DIR.iterdir()):
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")

    return app
