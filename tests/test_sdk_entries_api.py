"""API tests for DELETE /api/sessions/{session_id}/sdk-entries.

Covers the admin endpoint that discards the SDK transcript mirror while
keeping the Bearings session row alive.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bearings.db import sdk_entries as sdk_entries_db
from bearings.db import sessions as sessions_db
from bearings.db.connection import load_schema
from bearings.web.app import create_app


@pytest.fixture
async def app_and_db(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, aiosqlite.Connection]]:
    """FastAPI app wired to a fresh schema-loaded SQLite connection."""
    db_path = tmp_path / "sdk_entries_api.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        app = create_app(db_connection=conn)
        yield app, conn
    finally:
        await conn.close()


async def _new_chat(conn: aiosqlite.Connection) -> str:
    """Insert a minimal chat session row and return its id."""
    row = await sessions_db.create(
        conn,
        kind="chat",
        title="t",
        working_dir="/tmp/wd",
        model="sonnet",
    )
    return row.id


async def test_delete_sdk_entries_returns_204(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Happy path — existing session with entries returns 204 and entries are gone."""
    app, conn = app_and_db
    sid = await _new_chat(conn)
    await sdk_entries_db.append(
        conn,
        session_id=sid,
        entries=[{"type": "user", "content": "hello"}, {"type": "assistant", "content": "hi"}],
    )
    assert await sdk_entries_db.count_for_session(conn, session_id=sid) == 2

    with TestClient(app) as client:
        response = client.delete(f"/api/sessions/{sid}/sdk-entries")

    assert response.status_code == 204
    assert await sdk_entries_db.count_for_session(conn, session_id=sid) == 0


async def test_delete_sdk_entries_empty_session_returns_204(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Session exists but has no SDK entries — still 204 (idempotent)."""
    app, conn = app_and_db
    sid = await _new_chat(conn)

    with TestClient(app) as client:
        response = client.delete(f"/api/sessions/{sid}/sdk-entries")

    assert response.status_code == 204


async def test_delete_sdk_entries_unknown_session_returns_404(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Unknown session id returns 404."""
    app, _ = app_and_db
    with TestClient(app) as client:
        response = client.delete("/api/sessions/ses_nonexistent/sdk-entries")
    assert response.status_code == 404


async def test_delete_sdk_entries_session_row_survives(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """The Bearings session row is preserved — only the SDK mirror is cleared."""
    app, conn = app_and_db
    sid = await _new_chat(conn)
    await sdk_entries_db.append(conn, session_id=sid, entries=[{"type": "a"}])

    with TestClient(app) as client:
        client.delete(f"/api/sessions/{sid}/sdk-entries")
        get_response = client.get(f"/api/sessions/{sid}")

    assert get_response.status_code == 200
    assert get_response.json()["id"] == sid
