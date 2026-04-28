"""Integration tests for ``bearings.web.routes.tags`` via FastAPI.

Boots the real ASGI app via :class:`fastapi.testclient.TestClient` with
a freshly-bootstrapped DB on ``app.state.db_connection``; exercises
the full HTTP surface — CRUD, group filter, per-session attach/detach,
and the FK / unique-constraint error paths.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from bearings.db import get_connection_factory, load_schema
from bearings.web.app import create_app

_HEARTBEAT_S: Final[float] = 5.0


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[TestClient]:
    """Boot the app with a fresh DB connection on app.state."""
    db_path = tmp_path / "routes_tags.db"

    async def _open() -> aiosqlite.Connection:
        factory = get_connection_factory(db_path)
        conn = await factory()
        await load_schema(conn)
        return conn

    loop = asyncio.new_event_loop()
    try:
        conn = loop.run_until_complete(_open())
        # Seed one session so attach/detach FK paths are reachable.
        loop.run_until_complete(_seed_session(conn))
        app = create_app(heartbeat_interval_s=_HEARTBEAT_S, db_connection=conn)
        with TestClient(app) as client:
            yield client
        loop.run_until_complete(conn.close())
    finally:
        loop.close()


async def _seed_session(conn: aiosqlite.Connection) -> None:
    timestamp = "2026-04-28T12:00:00+00:00"
    await conn.execute(
        "INSERT INTO sessions (id, kind, title, working_dir, model, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("sess1", "chat", "Alpha", "/tmp/alpha", "sonnet", timestamp, timestamp),
    )
    await conn.commit()


def test_post_tag_creates_and_returns(app_client: TestClient) -> None:
    response = app_client.post(
        "/api/tags",
        json={
            "name": "bearings/architect",
            "color": "#ffaa00",
            "default_model": "opus",
            "working_dir": "/home/dave/proj",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "bearings/architect"
    assert body["group"] == "bearings"
    assert body["default_model"] == "opus"


def test_post_tag_409_on_duplicate_name(app_client: TestClient) -> None:
    app_client.post("/api/tags", json={"name": "dup"})
    response = app_client.post("/api/tags", json={"name": "dup"})
    assert response.status_code == 409


def test_post_tag_422_on_bad_default_model(app_client: TestClient) -> None:
    response = app_client.post(
        "/api/tags",
        json={"name": "x", "default_model": "not-a-model"},
    )
    assert response.status_code == 422


def test_get_tags_returns_alphabetical(app_client: TestClient) -> None:
    for n in ("z-tag", "a-tag", "m-tag"):
        app_client.post("/api/tags", json={"name": n})
    response = app_client.get("/api/tags")
    assert response.status_code == 200
    assert [t["name"] for t in response.json()] == ["a-tag", "m-tag", "z-tag"]


def test_get_tags_filters_by_group(app_client: TestClient) -> None:
    for n in ("bearings/a", "bearings/b", "general"):
        app_client.post("/api/tags", json={"name": n})
    response = app_client.get("/api/tags", params={"group": "bearings"})
    assert response.status_code == 200
    assert [t["name"] for t in response.json()] == ["bearings/a", "bearings/b"]


def test_get_tag_groups(app_client: TestClient) -> None:
    for n in ("bearings/a", "research/b", "general"):
        app_client.post("/api/tags", json={"name": n})
    response = app_client.get("/api/tag-groups")
    assert response.status_code == 200
    assert response.json() == ["bearings", "research"]


def test_get_tag_404_on_unknown_id(app_client: TestClient) -> None:
    response = app_client.get("/api/tags/99999")
    assert response.status_code == 404


def test_patch_tag_replaces_fields(app_client: TestClient) -> None:
    created = app_client.post("/api/tags", json={"name": "orig"}).json()
    response = app_client.patch(
        f"/api/tags/{created['id']}",
        json={
            "name": "renamed",
            "color": "#000000",
            "default_model": "haiku",
            "working_dir": "/x",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "renamed"
    assert body["default_model"] == "haiku"


def test_patch_tag_404_on_unknown_id(app_client: TestClient) -> None:
    response = app_client.patch("/api/tags/99999", json={"name": "x"})
    assert response.status_code == 404


def test_delete_tag_204(app_client: TestClient) -> None:
    created = app_client.post("/api/tags", json={"name": "to-delete"}).json()
    response = app_client.delete(f"/api/tags/{created['id']}")
    assert response.status_code == 204
    # Idempotency: second delete yields 404.
    response2 = app_client.delete(f"/api/tags/{created['id']}")
    assert response2.status_code == 404


def test_attach_and_detach_tag(app_client: TestClient) -> None:
    created = app_client.post("/api/tags", json={"name": "attach-me"}).json()
    tag_id = created["id"]
    # Initially no tags on session.
    assert app_client.get("/api/sessions/sess1/tags").json() == []
    # Attach.
    response = app_client.put(f"/api/sessions/sess1/tags/{tag_id}")
    assert response.status_code == 200
    rows = app_client.get("/api/sessions/sess1/tags").json()
    assert [t["id"] for t in rows] == [tag_id]
    # Idempotent re-attach.
    response2 = app_client.put(f"/api/sessions/sess1/tags/{tag_id}")
    assert response2.status_code == 200
    # Detach.
    response3 = app_client.delete(f"/api/sessions/sess1/tags/{tag_id}")
    assert response3.status_code == 204
    assert app_client.get("/api/sessions/sess1/tags").json() == []
    # Detach again → 404.
    response4 = app_client.delete(f"/api/sessions/sess1/tags/{tag_id}")
    assert response4.status_code == 404


def test_attach_unknown_session_or_tag_404(app_client: TestClient) -> None:
    created = app_client.post("/api/tags", json={"name": "ok"}).json()
    response = app_client.put(f"/api/sessions/missing/tags/{created['id']}")
    assert response.status_code == 404
    response2 = app_client.put("/api/sessions/sess1/tags/99999")
    assert response2.status_code == 404
