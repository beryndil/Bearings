"""Integration tests for ``POST /api/sessions/{id}/prompt``.

Covers the behavior-doc-mandated 202 / 400 / 404 / 409 / 422 / 429
matrix per ``docs/behavior/prompt-endpoint.md``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bearings.agent.prompt_dispatch import RateLimiter
from bearings.config.constants import (
    PROMPT_ACK_QUEUED_KEY,
    PROMPT_ACK_SESSION_ID_KEY,
    SESSION_KIND_CHAT,
)
from bearings.db import sessions as sessions_db
from bearings.db.connection import load_schema
from bearings.web.app import create_app


@pytest.fixture
async def app_and_db(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, aiosqlite.Connection]]:
    db_path = tmp_path / "prompt.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        app = create_app(db_connection=conn, prompt_rate_limiter=RateLimiter())
        yield app, conn
    finally:
        await conn.close()


async def _new_chat_session(conn: aiosqlite.Connection) -> str:
    s = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title="t", working_dir="/wd", model="sonnet"
    )
    return s.id


async def test_post_prompt_returns_202_with_envelope(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat_session(conn)
    with TestClient(app) as client:
        response = client.post(f"/api/sessions/{sid}/prompt", json={"content": "hello"})
    assert response.status_code == 202
    body = response.json()
    assert body[PROMPT_ACK_QUEUED_KEY] is True
    assert body[PROMPT_ACK_SESSION_ID_KEY] == sid
    assert response.headers["location"] == f"/api/sessions/{sid}"


async def test_post_prompt_persists_user_message(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    from bearings.db import messages as messages_db

    app, conn = app_and_db
    sid = await _new_chat_session(conn)
    with TestClient(app) as client:
        client.post(f"/api/sessions/{sid}/prompt", json={"content": "first"})
        client.post(f"/api/sessions/{sid}/prompt", json={"content": "second"})
    rows = await messages_db.list_for_session(conn, sid)
    assert [row.content for row in rows] == ["first", "second"]
    assert all(row.role == "user" for row in rows)


async def test_post_prompt_404_when_session_missing(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _conn = app_and_db
    with TestClient(app) as client:
        response = client.post("/api/sessions/ses_missing/prompt", json={"content": "x"})
    assert response.status_code == 404
    assert "ses_missing" in response.json()["detail"]


async def test_post_prompt_409_when_session_closed(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat_session(conn)
    await sessions_db.close(conn, sid)
    with TestClient(app) as client:
        response = client.post(f"/api/sessions/{sid}/prompt", json={"content": "x"})
    assert response.status_code == 409
    # Verbatim wording from behavior doc §"Failure responses".
    assert "session is closed" in response.json()["detail"]


async def test_post_prompt_400_when_content_whitespace(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat_session(conn)
    with TestClient(app) as client:
        response = client.post(f"/api/sessions/{sid}/prompt", json={"content": "   \n  "})
    assert response.status_code == 400


async def test_post_prompt_422_when_content_missing(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat_session(conn)
    with TestClient(app) as client:
        response = client.post(f"/api/sessions/{sid}/prompt", json={})
    assert response.status_code == 422


async def test_post_prompt_extra_fields_ignored(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Per behavior doc §"Request shape" — only ``content`` is read; additional
    fields are ignored at the boundary."""
    app, conn = app_and_db
    sid = await _new_chat_session(conn)
    with TestClient(app) as client:
        response = client.post(
            f"/api/sessions/{sid}/prompt",
            json={"content": "hi", "role": "system", "attachments": []},
        )
    assert response.status_code == 202


async def test_post_prompt_rate_limit_returns_429_with_retry_after(
    tmp_path: Path,
) -> None:
    """Tight rate limit (max=2 per long window) — third POST is 429."""
    db_path = tmp_path / "rl.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        limiter = RateLimiter(window_s=10, max_per_window=2)
        app = create_app(db_connection=conn, prompt_rate_limiter=limiter)
        sid = await _new_chat_session(conn)
        with TestClient(app) as client:
            r1 = client.post(f"/api/sessions/{sid}/prompt", json={"content": "a"})
            r2 = client.post(f"/api/sessions/{sid}/prompt", json={"content": "b"})
            r3 = client.post(f"/api/sessions/{sid}/prompt", json={"content": "c"})
        assert r1.status_code == 202
        assert r2.status_code == 202
        assert r3.status_code == 429
        assert "retry-after" in {key.lower() for key in r3.headers}
        assert int(r3.headers["retry-after"]) >= 1
    finally:
        await conn.close()


async def test_post_prompt_enqueues_on_runner(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Runner queue accumulates the dispatched prompts in arrival order."""
    app, conn = app_and_db
    sid = await _new_chat_session(conn)
    with TestClient(app) as client:
        client.post(f"/api/sessions/{sid}/prompt", json={"content": "a"})
        client.post(f"/api/sessions/{sid}/prompt", json={"content": "b"})
    runner = await app.state.runner_factory(sid)
    assert runner.prompt_queue_depth == 2
    first = runner.pop_next_prompt()
    second = runner.pop_next_prompt()
    assert first is not None and first.content == "a"
    assert second is not None and second.content == "b"


async def test_runner_factory_creates_runner_lazily(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Per behavior doc §"202 semantics" — endpoint lazily creates the
    runner if the target session has no live runner yet."""
    app, conn = app_and_db
    sid = await _new_chat_session(conn)
    # No runner before the POST.
    factory = app.state.runner_factory
    assert factory.get(sid) is None
    with TestClient(app) as client:
        client.post(f"/api/sessions/{sid}/prompt", json={"content": "hi"})
    assert factory.get(sid) is not None


async def test_post_prompt_rate_limit_per_session_isolation(
    tmp_path: Path,
) -> None:
    """Per behavior doc §"Rate-limit observable behavior" — "The rate
    limit is per-session, not global."
    """
    db_path = tmp_path / "iso.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        limiter = RateLimiter(window_s=10, max_per_window=1)
        app = create_app(db_connection=conn, prompt_rate_limiter=limiter)
        s1 = await _new_chat_session(conn)
        s2 = await _new_chat_session(conn)
        with TestClient(app) as client:
            r1a = client.post(f"/api/sessions/{s1}/prompt", json={"content": "x"})
            r1b = client.post(f"/api/sessions/{s1}/prompt", json={"content": "y"})
            r2 = client.post(f"/api/sessions/{s2}/prompt", json={"content": "z"})
        assert r1a.status_code == 202
        assert r1b.status_code == 429
        # s2's first POST under the same auth — independent window.
        assert r2.status_code == 202
    finally:
        await conn.close()
