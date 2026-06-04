"""Tests for POST/GET/DELETE /api/artifacts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bearings.db import sessions as sessions_db
from bearings.db.connection import load_schema
from bearings.web.app import create_app


@pytest.fixture
async def app_and_db(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, aiosqlite.Connection]]:
    db_path = tmp_path / "art.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        app = create_app(db_connection=conn)
        yield app, conn
    finally:
        await conn.close()


async def _new_session(conn: aiosqlite.Connection) -> str:
    s = await sessions_db.create(conn, kind="chat", title="t", working_dir="/wd", model="sonnet")
    return s.id


# ---------------------------------------------------------------------------
# Register (POST)
# ---------------------------------------------------------------------------


async def test_register_artifact_201(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
    tmp_path: Path,
) -> None:
    """POST /api/artifacts returns 201 and the new row."""
    app, conn = app_and_db
    session_id = await _new_session(conn)
    artifact_file = tmp_path / "out.png"
    artifact_file.write_bytes(b"\x89PNG")

    with TestClient(app) as client:
        resp = client.post(
            "/api/artifacts",
            json={
                "session_id": session_id,
                "path": str(artifact_file),
                "mime_type": "image/png",
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["session_id"] == session_id
    assert body["path"] == str(artifact_file)
    assert body["mime_type"] == "image/png"
    assert body["id"].startswith("art_")
    assert "created_at" in body


async def test_register_artifact_404_on_unknown_session(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
    tmp_path: Path,
) -> None:
    """POST /api/artifacts returns 404 when session does not exist."""
    app, _ = app_and_db
    with TestClient(app) as client:
        resp = client.post(
            "/api/artifacts",
            json={
                "session_id": "ses_doesnotexist0000000000000000000",
                "path": "/some/file.pdf",
                "mime_type": "application/pdf",
            },
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET artifact
# ---------------------------------------------------------------------------


async def test_get_artifact_serves_file(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
    tmp_path: Path,
) -> None:
    """GET /api/artifacts/{id} streams the file with Content-Disposition: inline."""
    app, conn = app_and_db
    session_id = await _new_session(conn)
    artifact_file = tmp_path / "report.txt"
    artifact_file.write_text("hello artifact", encoding="utf-8")

    with TestClient(app) as client:
        reg = client.post(
            "/api/artifacts",
            json={
                "session_id": session_id,
                "path": str(artifact_file),
                "mime_type": "text/plain",
            },
        )
        assert reg.status_code == 201
        artifact_id = reg.json()["id"]

        serve = client.get(f"/api/artifacts/{artifact_id}")

    assert serve.status_code == 200
    assert serve.headers["content-disposition"] == "inline"
    assert b"hello artifact" in serve.content


async def test_get_artifact_404_missing(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """GET /api/artifacts/{id} returns 404 when the id is unknown."""
    app, _ = app_and_db
    with TestClient(app) as client:
        resp = client.get("/api/artifacts/art_notfound000000000000000000000000")
    assert resp.status_code == 404


async def test_get_artifact_404_file_absent(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
    tmp_path: Path,
) -> None:
    """GET /api/artifacts/{id} returns 404 when file is no longer on disk."""
    app, conn = app_and_db
    session_id = await _new_session(conn)
    artifact_file = tmp_path / "gone.txt"
    artifact_file.write_text("x", encoding="utf-8")

    with TestClient(app) as client:
        reg = client.post(
            "/api/artifacts",
            json={
                "session_id": session_id,
                "path": str(artifact_file),
                "mime_type": "text/plain",
            },
        )
        artifact_id = reg.json()["id"]
        artifact_file.unlink()  # remove the file
        serve = client.get(f"/api/artifacts/{artifact_id}")

    assert serve.status_code == 404


# ---------------------------------------------------------------------------
# DELETE artifact
# ---------------------------------------------------------------------------


async def test_delete_artifact_204(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
    tmp_path: Path,
) -> None:
    """DELETE /api/artifacts/{id} returns 204 and removes the file."""
    app, conn = app_and_db
    session_id = await _new_session(conn)
    artifact_file = tmp_path / "todelete.bin"
    artifact_file.write_bytes(b"data")

    with TestClient(app) as client:
        reg = client.post(
            "/api/artifacts",
            json={
                "session_id": session_id,
                "path": str(artifact_file),
                "mime_type": "application/octet-stream",
            },
        )
        artifact_id = reg.json()["id"]
        del_resp = client.delete(f"/api/artifacts/{artifact_id}")
        assert del_resp.status_code == 204

        # File should be deleted.
        assert not artifact_file.exists()

        # Subsequent GET should 404.
        get_resp = client.get(f"/api/artifacts/{artifact_id}")
        assert get_resp.status_code == 404


async def test_delete_artifact_404_missing(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """DELETE /api/artifacts/{id} returns 404 when the id is unknown."""
    app, _ = app_and_db
    with TestClient(app) as client:
        resp = client.delete("/api/artifacts/art_notfound000000000000000000000000")
    assert resp.status_code == 404
