"""Tests for GET /api/history/export."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bearings.db import messages as messages_db
from bearings.db import sessions as sessions_db
from bearings.db import tags as tags_db
from bearings.db.connection import load_schema
from bearings.web.app import create_app


@pytest.fixture
async def app_and_db(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, aiosqlite.Connection]]:
    db_path = tmp_path / "exp.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        app = create_app(db_connection=conn)
        yield app, conn
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Export shape tests
# ---------------------------------------------------------------------------


def test_export_response_shape(app_and_db: tuple[FastAPI, aiosqlite.Connection]) -> None:
    """GET /api/history/export returns sessions, messages, and tags keys."""
    app, _ = app_and_db
    with TestClient(app) as client:
        resp = client.get("/api/history/export")
    assert resp.status_code == 200
    body = resp.json()
    assert "sessions" in body
    assert "messages" in body
    assert "tags" in body
    assert isinstance(body["sessions"], list)
    assert isinstance(body["messages"], dict)
    assert isinstance(body["tags"], dict)


def test_export_empty_db(app_and_db: tuple[FastAPI, aiosqlite.Connection]) -> None:
    """An empty DB returns empty collections."""
    app, _ = app_and_db
    with TestClient(app) as client:
        resp = client.get("/api/history/export")
    body = resp.json()
    assert body["sessions"] == []
    assert body["messages"] == {}
    assert body["tags"] == {}


async def test_export_includes_sessions(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Exported sessions list contains all created sessions."""
    app, conn = app_and_db
    s1 = await sessions_db.create(
        conn, kind="chat", title="Session A", working_dir="/wd", model="sonnet"
    )
    s2 = await sessions_db.create(
        conn, kind="chat", title="Session B", working_dir="/wd", model="sonnet"
    )
    await conn.commit()

    with TestClient(app) as client:
        resp = client.get("/api/history/export")
    body = resp.json()
    exported_ids = {s["id"] for s in body["sessions"]}
    assert s1.id in exported_ids
    assert s2.id in exported_ids


async def test_export_session_fields(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Each session entry in the export has required fields."""
    app, conn = app_and_db
    await sessions_db.create(conn, kind="chat", title="Detailed", working_dir="/wd", model="sonnet")
    await conn.commit()

    with TestClient(app) as client:
        resp = client.get("/api/history/export")
    body = resp.json()
    assert len(body["sessions"]) == 1
    entry = body["sessions"][0]
    for field in ("id", "kind", "title", "working_dir", "model", "created_at", "updated_at"):
        assert field in entry, f"Missing field {field!r} in exported session"


async def test_export_includes_messages(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Messages are keyed by session_id in the export."""
    app, conn = app_and_db
    session = await sessions_db.create(
        conn, kind="chat", title="T", working_dir="/wd", model="sonnet"
    )
    await messages_db.insert_user(conn, session_id=session.id, content="hello")
    await conn.commit()

    with TestClient(app) as client:
        resp = client.get("/api/history/export")
    body = resp.json()
    assert session.id in body["messages"]
    msgs = body["messages"][session.id]
    assert len(msgs) == 1
    assert msgs[0]["content"] == "hello"
    assert msgs[0]["role"] == "user"


async def test_export_includes_tags(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Tags are keyed by session_id in the export."""
    app, conn = app_and_db
    session = await sessions_db.create(
        conn, kind="chat", title="T", working_dir="/wd", model="sonnet"
    )
    tag = await tags_db.create(conn, name="my-tag", class_="general")
    await tags_db.set_for_session(conn, session_id=session.id, tag_ids=(tag.id,))
    await conn.commit()

    with TestClient(app) as client:
        resp = client.get("/api/history/export")
    body = resp.json()
    assert session.id in body["tags"]
    tag_names = [t["name"] for t in body["tags"][session.id]]
    assert "my-tag" in tag_names


def test_export_503_without_db() -> None:
    """GET /api/history/export returns 503 when no DB is configured."""
    app = create_app()  # no db_connection
    with TestClient(app) as client:
        resp = client.get("/api/history/export")
    assert resp.status_code == 503
