"""Run-control endpoint tests for ``bearings.web.routes.checklists``.

Covers Start / Stop / Pause / Resume / Skip-current / Status state
transitions per behavior/checklists.md §"Run-control surface".
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
    AUTO_DRIVER_FAILURE_POLICY_HALT,
    AUTO_DRIVER_FAILURE_POLICY_SKIP,
    AUTO_DRIVER_STATE_PAUSED,
    AUTO_DRIVER_STATE_RUNNING,
)
from bearings.db import get_connection_factory, load_schema
from bearings.web.app import create_app

_HEARTBEAT_S: Final[float] = 5.0
_CHECKLIST_ID: Final[str] = "chk_runctrl"


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[TestClient]:
    db_path = tmp_path / "run_ctrl.db"

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


def test_start_run_201(app_client: TestClient) -> None:
    response = app_client.post(
        f"/api/checklists/{_CHECKLIST_ID}/run/start",
        json={"failure_policy": AUTO_DRIVER_FAILURE_POLICY_HALT},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["state"] == AUTO_DRIVER_STATE_RUNNING
    assert body["failure_policy"] == AUTO_DRIVER_FAILURE_POLICY_HALT
    assert body["visit_existing"] is False


def test_start_with_skip_policy_and_visit_existing(app_client: TestClient) -> None:
    response = app_client.post(
        f"/api/checklists/{_CHECKLIST_ID}/run/start",
        json={
            "failure_policy": AUTO_DRIVER_FAILURE_POLICY_SKIP,
            "visit_existing": True,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["failure_policy"] == AUTO_DRIVER_FAILURE_POLICY_SKIP
    assert body["visit_existing"] is True


def test_start_rejects_unknown_failure_policy(app_client: TestClient) -> None:
    response = app_client.post(
        f"/api/checklists/{_CHECKLIST_ID}/run/start",
        json={"failure_policy": "bogus"},
    )
    assert response.status_code == 422


def test_start_409_when_already_active(app_client: TestClient) -> None:
    first = app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/start", json={})
    assert first.status_code == 201
    second = app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/start", json={})
    assert second.status_code == 409


def test_status_404_when_no_run(app_client: TestClient) -> None:
    response = app_client.get(f"/api/checklists/{_CHECKLIST_ID}/run/status")
    assert response.status_code == 404


def test_status_returns_active_run(app_client: TestClient) -> None:
    app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/start", json={})
    response = app_client.get(f"/api/checklists/{_CHECKLIST_ID}/run/status")
    assert response.status_code == 200
    assert response.json()["state"] == AUTO_DRIVER_STATE_RUNNING


def test_stop_transitions_to_paused(app_client: TestClient) -> None:
    app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/start", json={})
    response = app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/stop")
    assert response.status_code == 200
    assert response.json()["state"] == AUTO_DRIVER_STATE_PAUSED


def test_stop_404_when_no_active_run(app_client: TestClient) -> None:
    response = app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/stop")
    assert response.status_code == 404


def test_pause_is_alias_of_stop(app_client: TestClient) -> None:
    app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/start", json={})
    response = app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/pause")
    assert response.status_code == 200
    assert response.json()["state"] == AUTO_DRIVER_STATE_PAUSED


def test_resume_from_paused(app_client: TestClient) -> None:
    app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/start", json={})
    app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/stop")
    response = app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/resume")
    assert response.status_code == 200
    assert response.json()["state"] == AUTO_DRIVER_STATE_RUNNING


def test_resume_409_when_not_paused(app_client: TestClient) -> None:
    app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/start", json={})
    # Currently running, not paused
    response = app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/resume")
    assert response.status_code == 409


def test_resume_404_when_no_run(app_client: TestClient) -> None:
    response = app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/resume")
    assert response.status_code == 404


def test_skip_current_signals_registry(app_client: TestClient) -> None:
    app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/start", json={})
    response = app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/skip-current")
    # Even with no live driver registered, the route succeeds (the
    # registry signal is best-effort) — durable run row is unchanged.
    assert response.status_code == 200


def test_skip_current_404_when_no_run(app_client: TestClient) -> None:
    response = app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/skip-current")
    assert response.status_code == 404


def test_overview_includes_active_run_after_start(app_client: TestClient) -> None:
    app_client.post(f"/api/checklists/{_CHECKLIST_ID}/run/start", json={})
    response = app_client.get(f"/api/checklists/{_CHECKLIST_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["active_run"] is not None
    assert body["active_run"]["state"] == AUTO_DRIVER_STATE_RUNNING
