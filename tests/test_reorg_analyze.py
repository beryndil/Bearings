"""Tests for POST /api/sessions/{id}/reorg/analyze (N-11/R-2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bearings.config.constants import SESSION_KIND_CHAT
from bearings.db import messages as messages_db
from bearings.db import sessions as sessions_db
from bearings.db.connection import load_schema
from bearings.web.app import create_app


@pytest.fixture
async def app_and_db(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, aiosqlite.Connection]]:
    db_path = tmp_path / "reorg_analyze.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        app = create_app(db_connection=conn)
        yield app, conn
    finally:
        await conn.close()


async def _new_chat(conn: aiosqlite.Connection, title: str = "session") -> str:
    session = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title=title, working_dir="/wd", model="sonnet"
    )
    return session.id


async def _add_msg(conn: aiosqlite.Connection, session_id: str, content: str = "hi") -> str:
    msg = await messages_db.insert_user(conn, session_id=session_id, content=content)
    return msg.id


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


async def test_analyze_empty_session_returns_empty_proposals(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat(conn)
    with TestClient(app) as client:
        resp = client.post(f"/api/sessions/{sid}/reorg/analyze")
    assert resp.status_code == 200
    body = resp.json()
    assert body["proposals"] == []
    assert body["source"] == "heuristic"


async def test_analyze_single_message_no_proposals(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat(conn)
    await _add_msg(conn, sid, "hello")
    with TestClient(app) as client:
        resp = client.post(f"/api/sessions/{sid}/reorg/analyze")
    assert resp.status_code == 200
    assert resp.json()["proposals"] == []


async def test_analyze_chunk_boundary_proposed(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """With chunk_size=3, a boundary should be proposed at message index 3."""
    app, conn = app_and_db
    sid = await _new_chat(conn)
    for i in range(5):
        await _add_msg(conn, sid, f"msg {i}")
    with TestClient(app) as client:
        resp = client.post(f"/api/sessions/{sid}/reorg/analyze", params={"chunk_size": 3})
    assert resp.status_code == 200
    body = resp.json()
    proposals = body["proposals"]
    # idx=3 should produce a chunk proposal: "Natural chunk boundary at message 4"
    assert any("chunk boundary" in p["reason"].lower() for p in proposals)
    assert all("message_id" in p and "reason" in p for p in proposals)


# ---------------------------------------------------------------------------
# 404 for unknown session
# ---------------------------------------------------------------------------


async def test_analyze_404_for_unknown_session(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _ = app_and_db
    with TestClient(app) as client:
        resp = client.post("/api/sessions/ses_doesnotexist/reorg/analyze")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# chunk_size validation
# ---------------------------------------------------------------------------


async def test_analyze_422_when_chunk_size_too_small(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat(conn)
    with TestClient(app) as client:
        resp = client.post(f"/api/sessions/{sid}/reorg/analyze", params={"chunk_size": 1})
    assert resp.status_code == 422
