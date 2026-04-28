"""Integration tests for ``bearings.web.routes.checklists`` via FastAPI.

Covers the picking / linking / reordering / run-control endpoint
categories from ``docs/behavior/checklists.md``. Each test exercises
the FastAPI handler end-to-end against a freshly-loaded schema.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from bearings.config.constants import (
    ITEM_OUTCOME_BLOCKED,
    ITEM_OUTCOME_FAILED,
    ITEM_OUTCOME_SKIPPED,
    PAIRED_CHAT_SPAWNED_BY_USER,
)
from bearings.db import get_connection_factory, load_schema
from bearings.web.app import create_app

_HEARTBEAT_S: Final[float] = 5.0
_CHECKLIST_ID: Final[str] = "chk_routes"


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[TestClient]:
    db_path = tmp_path / "routes_checklists.db"

    async def _open() -> aiosqlite.Connection:
        factory = get_connection_factory(db_path)
        conn = await factory()
        await load_schema(conn)
        await conn.execute(
            "INSERT INTO sessions (id, kind, title, working_dir, model, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                _CHECKLIST_ID,
                "checklist",
                "T",
                "/tmp",
                "sonnet",
                "2026-01-01",
                "2026-01-01",
            ),
        )
        # Pre-seed a chat-kind session for link tests
        await conn.execute(
            "INSERT INTO sessions (id, kind, title, working_dir, model, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "chat_link",
                "chat",
                "L",
                "/tmp",
                "sonnet",
                "2026-01-01",
                "2026-01-01",
            ),
        )
        await conn.commit()
        return conn

    loop = asyncio.new_event_loop()
    try:
        conn = loop.run_until_complete(_open())
        app = create_app(heartbeat_interval_s=_HEARTBEAT_S, db_connection=conn)
        with TestClient(app) as client:
            yield client
        loop.run_until_complete(conn.close())
    finally:
        loop.close()


def _create_item(client: TestClient, label: str, **kwargs: object) -> int:
    response = client.post(
        f"/api/checklists/{_CHECKLIST_ID}/items",
        json={"label": label, **kwargs},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


# ---- create / read --------------------------------------------------------


def test_create_item_201(app_client: TestClient) -> None:
    response = app_client.post(
        f"/api/checklists/{_CHECKLIST_ID}/items",
        json={"label": "first"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["label"] == "first"
    assert body["parent_item_id"] is None


def test_create_item_422_on_empty_label(app_client: TestClient) -> None:
    response = app_client.post(
        f"/api/checklists/{_CHECKLIST_ID}/items",
        json={"label": ""},
    )
    assert response.status_code == 422


def test_create_child_item_under_parent(app_client: TestClient) -> None:
    parent = _create_item(app_client, "P")
    response = app_client.post(
        f"/api/checklists/{_CHECKLIST_ID}/items",
        json={"label": "C", "parent_item_id": parent},
    )
    assert response.status_code == 201
    assert response.json()["parent_item_id"] == parent


def test_list_items(app_client: TestClient) -> None:
    _create_item(app_client, "A")
    _create_item(app_client, "B")
    response = app_client.get(f"/api/checklists/{_CHECKLIST_ID}/items")
    assert response.status_code == 200
    labels = [item["label"] for item in response.json()]
    assert labels == ["A", "B"]


def test_get_overview_bundles_active_run(app_client: TestClient) -> None:
    _create_item(app_client, "A")
    response = app_client.get(f"/api/checklists/{_CHECKLIST_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["checklist_id"] == _CHECKLIST_ID
    assert body["active_run"] is None
    assert len(body["items"]) == 1


def test_get_item_404(app_client: TestClient) -> None:
    response = app_client.get("/api/checklist-items/99999")
    assert response.status_code == 404


def test_get_item_round_trip(app_client: TestClient) -> None:
    item_id = _create_item(app_client, "A")
    response = app_client.get(f"/api/checklist-items/{item_id}")
    assert response.status_code == 200
    assert response.json()["label"] == "A"


# ---- update / delete -----------------------------------------------------


def test_patch_item_updates_label(app_client: TestClient) -> None:
    item_id = _create_item(app_client, "A")
    response = app_client.patch(
        f"/api/checklist-items/{item_id}",
        json={"label": "A-prime"},
    )
    assert response.status_code == 200
    assert response.json()["label"] == "A-prime"


def test_patch_item_updates_notes(app_client: TestClient) -> None:
    item_id = _create_item(app_client, "A")
    response = app_client.patch(
        f"/api/checklist-items/{item_id}",
        json={"notes": "some notes"},
    )
    assert response.status_code == 200
    assert response.json()["notes"] == "some notes"


def test_patch_item_404(app_client: TestClient) -> None:
    response = app_client.patch("/api/checklist-items/99999", json={"label": "x"})
    assert response.status_code == 404


def test_patch_rejects_extra_keys(app_client: TestClient) -> None:
    item_id = _create_item(app_client, "A")
    response = app_client.patch(
        f"/api/checklist-items/{item_id}",
        json={"random": "x"},
    )
    assert response.status_code == 422


def test_delete_item_204(app_client: TestClient) -> None:
    item_id = _create_item(app_client, "A")
    response = app_client.delete(f"/api/checklist-items/{item_id}")
    assert response.status_code == 204
    # Idempotent 404 on second delete
    response2 = app_client.delete(f"/api/checklist-items/{item_id}")
    assert response2.status_code == 404


# ---- check / uncheck / block / unblock ----------------------------------


def test_check_item_marks_green(app_client: TestClient) -> None:
    item_id = _create_item(app_client, "A")
    response = app_client.post(f"/api/checklist-items/{item_id}/check")
    assert response.status_code == 200
    assert response.json()["checked_at"] is not None


def test_uncheck_clears(app_client: TestClient) -> None:
    item_id = _create_item(app_client, "A")
    app_client.post(f"/api/checklist-items/{item_id}/check")
    response = app_client.post(f"/api/checklist-items/{item_id}/uncheck")
    assert response.status_code == 200
    assert response.json()["checked_at"] is None


def test_check_404(app_client: TestClient) -> None:
    response = app_client.post("/api/checklist-items/99999/check")
    assert response.status_code == 404


def test_block_item_with_each_category(app_client: TestClient) -> None:
    for category in (ITEM_OUTCOME_BLOCKED, ITEM_OUTCOME_FAILED, ITEM_OUTCOME_SKIPPED):
        item_id = _create_item(app_client, f"task-{category}")
        response = app_client.post(
            f"/api/checklist-items/{item_id}/block",
            json={"category": category, "reason": "why"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["blocked_reason_category"] == category
        assert body["blocked_reason_text"] == "why"


def test_block_rejects_unknown_category(app_client: TestClient) -> None:
    item_id = _create_item(app_client, "A")
    response = app_client.post(
        f"/api/checklist-items/{item_id}/block",
        json={"category": "bogus"},
    )
    assert response.status_code == 422


def test_unblock_clears(app_client: TestClient) -> None:
    item_id = _create_item(app_client, "A")
    app_client.post(
        f"/api/checklist-items/{item_id}/block",
        json={"category": ITEM_OUTCOME_BLOCKED},
    )
    response = app_client.post(f"/api/checklist-items/{item_id}/unblock")
    assert response.status_code == 200
    assert response.json()["blocked_at"] is None


# ---- linking -------------------------------------------------------------


def test_link_chat_to_leaf(app_client: TestClient) -> None:
    item_id = _create_item(app_client, "leaf")
    response = app_client.post(
        f"/api/checklist-items/{item_id}/link",
        json={
            "chat_session_id": "chat_link",
            "spawned_by": PAIRED_CHAT_SPAWNED_BY_USER,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["chat_session_id"] == "chat_link"


def test_link_rejects_parent(app_client: TestClient) -> None:
    parent = _create_item(app_client, "P")
    _create_item(app_client, "C", parent_item_id=parent)
    response = app_client.post(
        f"/api/checklist-items/{parent}/link",
        json={"chat_session_id": "chat_link"},
    )
    assert response.status_code == 422


def test_link_rejects_unknown_spawned_by(app_client: TestClient) -> None:
    item_id = _create_item(app_client, "L")
    response = app_client.post(
        f"/api/checklist-items/{item_id}/link",
        json={"chat_session_id": "chat_link", "spawned_by": "bogus"},
    )
    assert response.status_code == 422


def test_unlink_clears_pointer(app_client: TestClient) -> None:
    item_id = _create_item(app_client, "L")
    app_client.post(
        f"/api/checklist-items/{item_id}/link",
        json={"chat_session_id": "chat_link"},
    )
    response = app_client.post(f"/api/checklist-items/{item_id}/unlink")
    assert response.status_code == 200
    assert response.json()["chat_session_id"] is None


def test_list_legs_returns_one_per_link(app_client: TestClient) -> None:
    item_id = _create_item(app_client, "L")
    app_client.post(
        f"/api/checklist-items/{item_id}/link",
        json={"chat_session_id": "chat_link"},
    )
    response = app_client.get(f"/api/checklist-items/{item_id}/legs")
    assert response.status_code == 200
    legs = response.json()
    assert len(legs) == 1
    assert legs[0]["leg_number"] == 1


# ---- reordering / nesting ---------------------------------------------


def test_move_to_new_parent(app_client: TestClient) -> None:
    a = _create_item(app_client, "A")
    b = _create_item(app_client, "B")
    response = app_client.post(
        f"/api/checklist-items/{b}/move",
        json={"parent_item_id": a},
    )
    assert response.status_code == 200
    assert response.json()["parent_item_id"] == a


def test_move_rejects_self_parent(app_client: TestClient) -> None:
    a = _create_item(app_client, "A")
    response = app_client.post(
        f"/api/checklist-items/{a}/move",
        json={"parent_item_id": a},
    )
    assert response.status_code == 422


def test_indent_under_previous_sibling(app_client: TestClient) -> None:
    a = _create_item(app_client, "A")
    b = _create_item(app_client, "B")
    response = app_client.post(f"/api/checklist-items/{b}/indent")
    assert response.status_code == 200
    assert response.json()["parent_item_id"] == a


def test_outdent_at_root_is_noop(app_client: TestClient) -> None:
    a = _create_item(app_client, "A")
    response = app_client.post(f"/api/checklist-items/{a}/outdent")
    assert response.status_code == 200
    assert response.json()["parent_item_id"] is None


def test_outdent_404(app_client: TestClient) -> None:
    response = app_client.post("/api/checklist-items/99999/outdent")
    assert response.status_code == 404
