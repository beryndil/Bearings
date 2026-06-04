"""Tests for GET /api/reply_actions/catalog and POST /api/sessions/{id}/reply_actions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import bearings.web.routes.reply_actions as reply_actions_mod
from bearings.db import sessions as sessions_db
from bearings.db.connection import load_schema
from bearings.web.app import create_app


@pytest.fixture
async def app_and_db(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, aiosqlite.Connection]]:
    db_path = tmp_path / "ra.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        app = create_app(db_connection=conn)
        yield app, conn
    finally:
        await conn.close()


async def _new_chat(conn: aiosqlite.Connection) -> str:
    s = await sessions_db.create(conn, kind="chat", title="t", working_dir="/wd", model="sonnet")
    return s.id


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_catalog_returns_list(app_and_db: tuple[FastAPI, aiosqlite.Connection]) -> None:
    app, _ = app_and_db
    with TestClient(app) as client:
        resp = client.get("/api/reply_actions/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 3


def test_catalog_entries_have_required_fields(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _ = app_and_db
    with TestClient(app) as client:
        resp = client.get("/api/reply_actions/catalog")
    for entry in resp.json():
        assert "id" in entry
        assert "label" in entry
        assert "description" in entry
        assert "instruction" in entry
        assert isinstance(entry["id"], str) and entry["id"]
        assert isinstance(entry["instruction"], str) and entry["instruction"]


def test_catalog_contains_required_ids(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _ = app_and_db
    with TestClient(app) as client:
        resp = client.get("/api/reply_actions/catalog")
    ids = {entry["id"] for entry in resp.json()}
    assert "summarize" in ids
    assert "reformat" in ids
    assert "translate_plain" in ids


# ---------------------------------------------------------------------------
# Apply — 404 on unknown session
# ---------------------------------------------------------------------------


def test_apply_404_on_unknown_session(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _ = app_and_db
    with TestClient(app) as client:
        resp = client.post(
            "/api/sessions/ses_unknown99999999999999999999999999/reply_actions",
            json={"source_content": "hello", "transformation_id": "summarize"},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Apply — mock advisor call, check response shape
# ---------------------------------------------------------------------------


async def test_apply_returns_content(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a mocked run_transform, the route returns the transformed content."""
    app, conn = app_and_db
    session_id = await _new_chat(conn)

    async def _mock_transform(content: str, instruction: str) -> str:
        return f"MOCK: {content[:20]}"

    monkeypatch.setattr(reply_actions_mod, "run_transform", _mock_transform)

    with TestClient(app) as client:
        resp = client.post(
            f"/api/sessions/{session_id}/reply_actions",
            json={"source_content": "original text", "transformation_id": "summarize"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "content" in body
    assert "MOCK: original text" in body["content"]
    assert body["transformation_id"] == "summarize"
    assert body["inserted"] is False


async def test_apply_invalid_transformation_id(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown transformation_id returns 422."""
    app, conn = app_and_db
    session_id = await _new_chat(conn)

    async def _mock_transform(content: str, instruction: str) -> str:
        return content  # should not be reached

    monkeypatch.setattr(reply_actions_mod, "run_transform", _mock_transform)

    with TestClient(app) as client:
        resp = client.post(
            f"/api/sessions/{session_id}/reply_actions",
            json={"source_content": "text", "transformation_id": "nonexistent_id"},
        )
    assert resp.status_code == 422
