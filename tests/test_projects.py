from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from twrminal.db.store import (
    NO_PROJECT,
    attach_tag,
    create_project,
    create_session,
    create_tag,
    delete_project,
    get_project,
    init_db,
    list_projects,
    list_sessions,
    update_project,
    update_session,
)

# --- store -----------------------------------------------------------


@pytest.mark.asyncio
async def test_create_project_returns_row_with_defaults(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        row = await create_project(conn, name="Twrminal")
        assert row["id"] >= 1
        assert row["name"] == "Twrminal"
        assert row["description"] is None
        assert row["system_prompt"] is None
        assert row["working_dir"] is None
        assert row["default_model"] is None
        assert row["pinned"] == 0
        assert row["sort_order"] == 0
        assert row["created_at"]
        assert row["updated_at"] == row["created_at"]
        assert row["session_count"] == 0
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_create_project_rejects_duplicate_name(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        await create_project(conn, name="Twrminal")
        with pytest.raises(Exception) as excinfo:
            await create_project(conn, name="Twrminal")
        assert "UNIQUE" in str(excinfo.value)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_list_projects_orders_pinned_then_sort_then_id(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        a = await create_project(conn, name="a", sort_order=10)
        b = await create_project(conn, name="b", sort_order=5)
        c = await create_project(conn, name="c", pinned=True, sort_order=100)
        d = await create_project(conn, name="d", pinned=True, sort_order=1)
        rows = await list_projects(conn)
        assert [r["id"] for r in rows] == [d["id"], c["id"], b["id"], a["id"]]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_list_projects_includes_session_count(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        proj = await create_project(conn, name="Twrminal")
        await create_session(conn, working_dir="/a", model="m", project_id=proj["id"])
        await create_session(conn, working_dir="/b", model="m", project_id=proj["id"])
        await create_session(conn, working_dir="/c", model="m")
        rows = await list_projects(conn)
        assert rows[0]["session_count"] == 2
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_update_project_applies_partial_fields(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        row = await create_project(conn, name="Twrminal")
        updated = await update_project(
            conn,
            row["id"],
            fields={"description": "Localhost UI", "pinned": True},
        )
        assert updated is not None
        assert updated["description"] == "Localhost UI"
        assert updated["pinned"] == 1
        # name left alone
        assert updated["name"] == "Twrminal"
        # updated_at bumped
        assert updated["updated_at"] >= row["updated_at"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_update_project_returns_none_for_missing(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        assert await update_project(conn, 999, fields={"name": "x"}) is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_delete_project_returns_false_for_missing(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        assert await delete_project(conn, 999) is False
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_delete_project_nulls_session_project_id(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        proj = await create_project(conn, name="Twrminal")
        sess = await create_session(conn, working_dir="/x", model="m", project_id=proj["id"])
        assert await delete_project(conn, proj["id"]) is True
        # session survives; project_id is now NULL
        async with conn.execute(
            "SELECT project_id FROM sessions WHERE id = ?", (sess["id"],)
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        assert row[0] is None
        assert await get_project(conn, proj["id"]) is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_create_session_accepts_project_id(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        proj = await create_project(conn, name="Twrminal")
        sess = await create_session(conn, working_dir="/x", model="m", project_id=proj["id"])
        assert sess["project_id"] == proj["id"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_update_session_accepts_project_id_and_clears_it(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        proj = await create_project(conn, name="Twrminal")
        sess = await create_session(conn, working_dir="/x", model="m")
        assigned = await update_session(conn, sess["id"], fields={"project_id": proj["id"]})
        assert assigned is not None
        assert assigned["project_id"] == proj["id"]
        cleared = await update_session(conn, sess["id"], fields={"project_id": None})
        assert cleared is not None
        assert cleared["project_id"] is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_list_sessions_filter_by_project_id(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        proj_a = await create_project(conn, name="A")
        proj_b = await create_project(conn, name="B")
        s1 = await create_session(conn, working_dir="/1", model="m", project_id=proj_a["id"])
        s2 = await create_session(conn, working_dir="/2", model="m", project_id=proj_a["id"])
        s3 = await create_session(conn, working_dir="/3", model="m", project_id=proj_b["id"])
        s4 = await create_session(conn, working_dir="/4", model="m")
        in_a = await list_sessions(conn, project_id=proj_a["id"])
        assert {r["id"] for r in in_a} == {s1["id"], s2["id"]}
        in_b = await list_sessions(conn, project_id=proj_b["id"])
        assert {r["id"] for r in in_b} == {s3["id"]}
        unscoped = await list_sessions(conn, project_id=NO_PROJECT)
        assert {r["id"] for r in unscoped} == {s4["id"]}
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_list_sessions_combines_project_and_tag_filters(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        proj = await create_project(conn, name="P")
        tag = await create_tag(conn, name="bug")
        s1 = await create_session(conn, working_dir="/1", model="m", project_id=proj["id"])
        # In-project but no tag — should be filtered out.
        await create_session(conn, working_dir="/2", model="m", project_id=proj["id"])
        s3 = await create_session(conn, working_dir="/3", model="m")
        await attach_tag(conn, s1["id"], tag["id"])
        # Tagged but no project — should also be filtered out.
        await attach_tag(conn, s3["id"], tag["id"])
        rows = await list_sessions(conn, project_id=proj["id"], tag_ids=[tag["id"]])
        assert {r["id"] for r in rows} == {s1["id"]}
    finally:
        await conn.close()


# --- API -------------------------------------------------------------


def _create_session(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    body = {"working_dir": "/tmp", "model": "claude-sonnet-4-6", **kwargs}
    resp = client.post("/api/sessions", json=body)
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()
    return data


def test_get_projects_empty(client: TestClient) -> None:
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert resp.json() == []


def test_post_project_returns_201_and_row(client: TestClient) -> None:
    resp = client.post(
        "/api/projects",
        json={
            "name": "Twrminal",
            "description": "Localhost UI",
            "system_prompt": "Prefer SQL over ORMs.",
            "pinned": True,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Twrminal"
    assert body["description"] == "Localhost UI"
    assert body["system_prompt"] == "Prefer SQL over ORMs."
    assert body["pinned"] is True
    assert body["sort_order"] == 0
    assert body["session_count"] == 0
    assert body["id"] >= 1


def test_post_project_duplicate_name_is_409(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "Twrminal"})
    resp = client.post("/api/projects", json={"name": "Twrminal"})
    assert resp.status_code == 409


def test_get_project_round_trip(client: TestClient) -> None:
    created = client.post("/api/projects", json={"name": "Twrminal"}).json()
    resp = client.get(f"/api/projects/{created['id']}")
    assert resp.status_code == 200
    assert resp.json() == created


def test_get_project_missing_is_404(client: TestClient) -> None:
    resp = client.get("/api/projects/999")
    assert resp.status_code == 404


def test_patch_project_updates_fields(client: TestClient) -> None:
    created = client.post("/api/projects", json={"name": "Twrminal"}).json()
    resp = client.patch(
        f"/api/projects/{created['id']}",
        json={"pinned": True, "system_prompt": "Use pacman."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pinned"] is True
    assert body["system_prompt"] == "Use pacman."
    assert body["name"] == "Twrminal"


def test_patch_project_duplicate_name_is_409(client: TestClient) -> None:
    a = client.post("/api/projects", json={"name": "a"}).json()
    client.post("/api/projects", json={"name": "b"})
    resp = client.patch(f"/api/projects/{a['id']}", json={"name": "b"})
    assert resp.status_code == 409


def test_patch_project_missing_is_404(client: TestClient) -> None:
    resp = client.patch("/api/projects/999", json={"name": "x"})
    assert resp.status_code == 404


def test_delete_project_is_204_and_nulls_sessions(client: TestClient) -> None:
    proj = client.post("/api/projects", json={"name": "Twrminal"}).json()
    sess = _create_session(client, project_id=proj["id"])
    resp = client.delete(f"/api/projects/{proj['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/projects/{proj['id']}").status_code == 404
    # Session survives but project_id is now null.
    refreshed = client.get(f"/api/sessions/{sess['id']}").json()
    assert refreshed["project_id"] is None


def test_delete_project_missing_is_404(client: TestClient) -> None:
    resp = client.delete("/api/projects/999")
    assert resp.status_code == 404


def test_post_session_with_project_id_roundtrips(client: TestClient) -> None:
    proj = client.post("/api/projects", json={"name": "Twrminal"}).json()
    sess = _create_session(client, project_id=proj["id"])
    assert sess["project_id"] == proj["id"]


def test_patch_session_accepts_project_id(client: TestClient) -> None:
    proj = client.post("/api/projects", json={"name": "Twrminal"}).json()
    sess = _create_session(client)
    assert sess["project_id"] is None
    resp = client.patch(f"/api/sessions/{sess['id']}", json={"project_id": proj["id"]})
    assert resp.status_code == 200
    assert resp.json()["project_id"] == proj["id"]
    # Clearing with explicit null works too.
    resp = client.patch(f"/api/sessions/{sess['id']}", json={"project_id": None})
    assert resp.status_code == 200
    assert resp.json()["project_id"] is None


def test_api_list_sessions_filters_by_project_id(client: TestClient) -> None:
    proj = client.post("/api/projects", json={"name": "Twrminal"}).json()
    in_project = _create_session(client, project_id=proj["id"])
    no_project = _create_session(client)
    scoped = client.get(f"/api/sessions?project_id={proj['id']}").json()
    assert {r["id"] for r in scoped} == {in_project["id"]}
    unscoped = client.get("/api/sessions?project_id=none").json()
    assert {r["id"] for r in unscoped} == {no_project["id"]}


def test_api_list_sessions_bad_project_id_is_400(client: TestClient) -> None:
    resp = client.get("/api/sessions?project_id=oops")
    assert resp.status_code == 400
