"""Tests for the Sunset response header middleware.

Per ``docs/deprecation-convention.md`` §3, routes carrying
``openapi_extra={"x-sunset": "v1.2.0"}`` emit a ``Sunset`` header.
These tests verify the middleware injects the header correctly on
deprecated routes and leaves non-deprecated routes untouched.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bearings.db.connection import load_schema
from bearings.web.app import create_app


@pytest.fixture
async def app_and_db(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, aiosqlite.Connection]]:
    """Create an app with a real DB so all routes are exercisable."""
    db_path = tmp_path / "sunset.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        app = create_app(db_connection=conn)
        yield app, conn
    finally:
        await conn.close()


def test_tag_groups_has_sunset_header(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """GET /api/tag-groups (deprecated) emits the Sunset header."""
    app, _ = app_and_db
    with TestClient(app) as client:
        response = client.get("/api/tag-groups")
    assert response.status_code == 200
    assert "Sunset" in response.headers
    # The date corresponds to v1.2.0 deprecation: 2027-01-01.
    assert "2027" in response.headers["Sunset"]
    assert "Jan" in response.headers["Sunset"]


def test_sessions_list_no_sunset_header(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """GET /api/sessions (not deprecated) has no Sunset header.

    The route has a deprecated *parameter* (tag_ids) but the route
    itself is not deprecated, so no Sunset header is emitted.
    """
    app, _ = app_and_db
    with TestClient(app) as client:
        response = client.get("/api/sessions")
    assert response.status_code == 200
    assert "Sunset" not in response.headers


def test_tags_list_no_sunset_header(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """GET /api/tags (not deprecated) has no Sunset header."""
    app, _ = app_and_db
    with TestClient(app) as client:
        response = client.get("/api/tags")
    assert response.status_code == 200
    assert "Sunset" not in response.headers


def test_health_no_sunset_header(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """GET /api/health (not deprecated) has no Sunset header."""
    app, _ = app_and_db
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert "Sunset" not in response.headers
