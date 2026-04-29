"""Integration tests for the session-row CRUD endpoints in
``web/routes/sessions.py`` (item 1.7 — auxiliary surface beside the
prompt endpoint)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bearings.config.constants import (
    SESSION_KIND_CHAT,
    SESSION_KIND_CHECKLIST,
)
from bearings.db import sessions as sessions_db
from bearings.db.connection import load_schema
from bearings.web.app import create_app


@pytest.fixture
async def app_and_db(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, aiosqlite.Connection]]:
    db_path = tmp_path / "sapi.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        app = create_app(db_connection=conn)
        yield app, conn
    finally:
        await conn.close()


async def _new_chat(conn: aiosqlite.Connection, title: str = "t") -> str:
    s = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title=title, working_dir="/wd", model="sonnet"
    )
    return s.id


async def test_list_sessions_returns_rows(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    await _new_chat(conn, "a")
    await _new_chat(conn, "b")
    with TestClient(app) as client:
        response = client.get("/api/sessions")
    assert response.status_code == 200
    titles = {row["title"] for row in response.json()}
    assert titles == {"a", "b"}


async def test_list_sessions_filter_by_kind(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    chat = await _new_chat(conn)
    cl = await sessions_db.create(
        conn, kind=SESSION_KIND_CHECKLIST, title="cl", working_dir="/wd", model="sonnet"
    )
    with TestClient(app) as client:
        chats = client.get("/api/sessions", params={"kind": "chat"})
        cls = client.get("/api/sessions", params={"kind": "checklist"})
    assert {row["id"] for row in chats.json()} == {chat}
    assert {row["id"] for row in cls.json()} == {cl.id}


async def test_list_sessions_invalid_kind_422(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _ = app_and_db
    with TestClient(app) as client:
        response = client.get("/api/sessions", params={"kind": "bogus"})
    assert response.status_code == 422


async def test_list_sessions_filter_open_only(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    open_id = await _new_chat(conn, "open")
    closed_id = await _new_chat(conn, "closed")
    await sessions_db.close(conn, closed_id)
    with TestClient(app) as client:
        response = client.get("/api/sessions", params={"include_closed": "false"})
    assert {row["id"] for row in response.json()} == {open_id}


async def test_get_session_round_trip(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat(conn, "the-title")
    with TestClient(app) as client:
        response = client.get(f"/api/sessions/{sid}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == sid
    assert body["title"] == "the-title"


async def test_get_session_404(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _ = app_and_db
    with TestClient(app) as client:
        response = client.get("/api/sessions/ses_missing")
    assert response.status_code == 404


async def test_patch_session_title(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat(conn, "old")
    with TestClient(app) as client:
        response = client.patch(f"/api/sessions/{sid}", json={"title": "new"})
    assert response.status_code == 200
    assert response.json()["title"] == "new"


async def test_patch_session_404(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _ = app_and_db
    with TestClient(app) as client:
        response = client.patch("/api/sessions/ses_missing", json={"title": "x"})
    assert response.status_code == 404


async def test_patch_session_empty_title_422(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat(conn)
    with TestClient(app) as client:
        response = client.patch(f"/api/sessions/{sid}", json={"title": ""})
    assert response.status_code == 422


async def test_close_session(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat(conn)
    with TestClient(app) as client:
        response = client.post(f"/api/sessions/{sid}/close")
    assert response.status_code == 200
    assert response.json()["closed_at"] is not None


async def test_close_session_404(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _ = app_and_db
    with TestClient(app) as client:
        response = client.post("/api/sessions/ses_missing/close")
    assert response.status_code == 404


async def test_reopen_session_round_trip(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat(conn)
    await sessions_db.close(conn, sid)
    with TestClient(app) as client:
        response = client.post(f"/api/sessions/{sid}/reopen")
    assert response.status_code == 200
    assert response.json()["closed_at"] is None


async def test_reopen_session_404(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _ = app_and_db
    with TestClient(app) as client:
        response = client.post("/api/sessions/ses_missing/reopen")
    assert response.status_code == 404


async def test_delete_session(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat(conn)
    with TestClient(app) as client:
        response = client.delete(f"/api/sessions/{sid}")
    assert response.status_code == 204
    assert await sessions_db.get(conn, sid) is None


async def test_delete_session_404(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _ = app_and_db
    with TestClient(app) as client:
        response = client.delete("/api/sessions/ses_missing")
    assert response.status_code == 404
