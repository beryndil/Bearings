# mypy: disable-error-code=explicit-any
"""Tests for POST /api/sessions/{id}/spawn_classify (T2-07).

Coverage:
* Endpoint responds 200 with the correct shape.
* classified flag persists across a subsequent GET /api/sessions/{id}.
* Empty session (no messages) → classified=False.
* Session with a credential pattern → classified=True, patterns_found non-empty.
* Unknown session → 404.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bearings.config.constants import MESSAGE_ID_PREFIX
from bearings.db import sessions as sessions_db
from bearings.db._id import new_id, now_iso
from bearings.db.connection import load_schema
from bearings.web.app import create_app


@pytest.fixture
async def app_and_db(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, aiosqlite.Connection]]:
    db_path = tmp_path / "classify.db"
    async with aiosqlite.connect(db_path) as conn:
        await load_schema(conn)
        yield create_app(db_connection=conn), conn


async def _make_session(db: aiosqlite.Connection, title: str = "t") -> str:
    row = await sessions_db.create(db, kind="chat", title=title, working_dir="/tmp", model="sonnet")
    return row.id


async def _insert_message(db: aiosqlite.Connection, session_id: str, content: str) -> None:
    """Insert a user message for testing the classifier."""
    msg_id = new_id(MESSAGE_ID_PREFIX)
    ts = now_iso()
    await db.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at) "
        "VALUES (?, ?, 'user', ?, ?)",
        (msg_id, session_id, content, ts),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Shape / response tests
# ---------------------------------------------------------------------------


async def test_spawn_classify_empty_session_returns_clean(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """An empty session (no messages) yields classified=False, patterns_found=[]."""
    app, db = app_and_db
    sid = await _make_session(db)
    with TestClient(app) as client:
        resp = client.post(f"/api/sessions/{sid}/spawn_classify")
    assert resp.status_code == 200
    body = resp.json()
    assert body["classified"] is False
    assert body["patterns_found"] == []
    assert isinstance(body["reason"], str)
    assert "session" in body
    assert body["session"]["id"] == sid
    # classified field must appear on the session snapshot too.
    assert body["session"]["classified"] is False


async def test_spawn_classify_flag_persists_across_refetch(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """After spawn_classify sets classified=True, GET /api/sessions/{id} returns it."""
    app, db = app_and_db
    sid = await _make_session(db)
    # Insert a message containing an API key pattern.
    await _insert_message(db, sid, "api_key=supersecrettoken123456")

    with TestClient(app) as client:
        classify_resp = client.post(f"/api/sessions/{sid}/spawn_classify")
        assert classify_resp.status_code == 200
        assert classify_resp.json()["classified"] is True

        # Re-fetch the session and confirm the flag is persisted.
        get_resp = client.get(f"/api/sessions/{sid}")
        assert get_resp.status_code == 200
        assert get_resp.json()["classified"] is True


async def test_spawn_classify_credential_pattern_detected(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """A message with an AWS key pattern triggers classification."""
    app, db = app_and_db
    sid = await _make_session(db)
    await _insert_message(db, sid, "Use key AKIAIOSFODNN7EXAMPLE for access")

    with TestClient(app) as client:
        resp = client.post(f"/api/sessions/{sid}/spawn_classify")
    assert resp.status_code == 200
    body = resp.json()
    assert body["classified"] is True
    assert "aws_key" in body["patterns_found"]


async def test_spawn_classify_unknown_session_404(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """POST to a non-existent session_id returns 404."""
    app, _ = app_and_db
    with TestClient(app) as client:
        resp = client.post("/api/sessions/ses_doesnotexist00000000000000000/spawn_classify")
    assert resp.status_code == 404


async def test_spawn_classify_idempotent_clean(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Calling spawn_classify twice on the same empty session is idempotent."""
    app, db = app_and_db
    sid = await _make_session(db)
    with TestClient(app) as client:
        r1 = client.post(f"/api/sessions/{sid}/spawn_classify")
        r2 = client.post(f"/api/sessions/{sid}/spawn_classify")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["classified"] is False
    assert r2.json()["classified"] is False
