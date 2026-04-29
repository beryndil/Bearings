"""Integration tests for ``POST /api/checklist-items/{id}/spawn-chat``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bearings.config.constants import (
    PAIRED_CHAT_SPAWNED_BY_DRIVER,
    SESSION_KIND_CHECKLIST,
)
from bearings.db import checklists as checklists_db
from bearings.db import sessions as sessions_db
from bearings.db.connection import load_schema
from bearings.web.app import create_app


@pytest.fixture
async def app_and_conn(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, aiosqlite.Connection]]:
    db_path = tmp_path / "pc-api.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        app = create_app(db_connection=conn)
        yield app, conn
    finally:
        await conn.close()


async def _new_checklist_with_leaf(conn: aiosqlite.Connection) -> tuple[str, int]:
    checklist = await sessions_db.create(
        conn,
        kind=SESSION_KIND_CHECKLIST,
        title="cl",
        working_dir="/parent/wd",
        model="sonnet",
    )
    item = await checklists_db.create(conn, checklist_id=checklist.id, label="leaf")
    return checklist.id, item.id


async def test_spawn_chat_201_on_first_call(
    app_and_conn: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_conn
    _cid, item_id = await _new_checklist_with_leaf(conn)
    with TestClient(app) as client:
        response = client.post(f"/api/checklist-items/{item_id}/spawn-chat", json={})
    assert response.status_code == 201
    body = response.json()
    assert body["chat_session_id"].startswith("ses_")
    assert body["item_id"] == item_id
    assert body["title"] == "leaf"
    assert body["working_dir"] == "/parent/wd"
    assert body["created"] is True


async def test_spawn_chat_200_on_idempotent_re_call(
    app_and_conn: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_conn
    _cid, item_id = await _new_checklist_with_leaf(conn)
    with TestClient(app) as client:
        first = client.post(f"/api/checklist-items/{item_id}/spawn-chat", json={})
        second = client.post(f"/api/checklist-items/{item_id}/spawn-chat", json={})
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["chat_session_id"] == first.json()["chat_session_id"]
    assert second.json()["created"] is False


async def test_spawn_chat_404_on_missing_item(
    app_and_conn: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _conn = app_and_conn
    with TestClient(app) as client:
        response = client.post("/api/checklist-items/9999/spawn-chat", json={})
    assert response.status_code == 404


async def test_spawn_chat_422_on_parent_item(
    app_and_conn: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_conn
    checklist_id, parent_id = await _new_checklist_with_leaf(conn)
    await checklists_db.create(
        conn, checklist_id=checklist_id, parent_item_id=parent_id, label="child"
    )
    with TestClient(app) as client:
        response = client.post(f"/api/checklist-items/{parent_id}/spawn-chat", json={})
    assert response.status_code == 422
    assert "parent" in response.json()["detail"]


async def test_spawn_chat_with_title_and_plug(
    app_and_conn: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_conn
    _cid, item_id = await _new_checklist_with_leaf(conn)
    with TestClient(app) as client:
        response = client.post(
            f"/api/checklist-items/{item_id}/spawn-chat",
            json={
                "title": "Custom",
                "plug": "leg-2 plug body",
                "spawned_by": PAIRED_CHAT_SPAWNED_BY_DRIVER,
            },
        )
    assert response.status_code == 201
    chat_id = response.json()["chat_session_id"]
    chat = await sessions_db.get(conn, chat_id)
    assert chat is not None
    assert chat.title == "Custom"
    assert chat.description == "leg-2 plug body"


async def test_spawn_chat_422_on_unknown_spawned_by(
    app_and_conn: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_conn
    _cid, item_id = await _new_checklist_with_leaf(conn)
    with TestClient(app) as client:
        response = client.post(
            f"/api/checklist-items/{item_id}/spawn-chat",
            json={"spawned_by": "bogus"},
        )
    assert response.status_code == 422
