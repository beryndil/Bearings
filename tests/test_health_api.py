"""Integration tests for ``bearings.web.routes.health`` (item 1.10)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from bearings.config.constants import HEALTH_STATUS_DEGRADED, HEALTH_STATUS_OK
from bearings.db import get_connection_factory, load_schema
from bearings.web.app import create_app

_HEARTBEAT_S: Final[float] = 5.0


@pytest.fixture
def app_client_with_db(tmp_path: Path) -> Iterator[TestClient]:
    db_path = tmp_path / "health.db"

    async def _open() -> aiosqlite.Connection:
        factory = get_connection_factory(db_path)
        conn = await factory()
        await load_schema(conn)
        return conn

    loop = asyncio.new_event_loop()
    try:
        conn = loop.run_until_complete(_open())
        app = create_app(heartbeat_interval_s=_HEARTBEAT_S, db_connection=conn)
        with TestClient(app) as client:
            yield client
        loop.run_until_complete(conn.close())
    finally:
        loop.close()


def test_health_returns_ok_with_db(app_client_with_db: TestClient) -> None:
    response = app_client_with_db.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == HEALTH_STATUS_OK
    assert body["db_ok"] is True
    assert body["uptime_s"] >= 0
    assert body["version"]


def test_health_degraded_without_db() -> None:
    app = create_app(heartbeat_interval_s=_HEARTBEAT_S)
    with TestClient(app) as client:
        response = client.get("/api/health")
        # Still 200 — health endpoint always returns 200 when alive.
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == HEALTH_STATUS_DEGRADED
        assert body["db_ok"] is False
