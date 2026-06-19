"""Tests for GET /api/sessions/running and GET /api/sessions/awaiting (M-11/R-1)."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from bearings.agent.runner import RunnerStatus
from bearings.web.app import create_app
from bearings.web.runner_factory import InProcessRunnerRegistry


@pytest.fixture
def client_with_registry() -> Iterator[tuple[TestClient, InProcessRunnerRegistry]]:
    """Boot the app with an empty registry attached to app.state."""
    app = create_app()
    registry = InProcessRunnerRegistry()
    app.state.runner_factory = registry
    with TestClient(app) as client:
        yield client, registry


def _make_runner_stub(is_running: bool, is_awaiting_user: bool) -> MagicMock:
    """Return a minimal SessionRunner stub."""
    stub = MagicMock()
    stub.status = RunnerStatus(
        is_running=is_running,
        is_awaiting_user=is_awaiting_user,
        routing_decision=None,
    )
    return stub


# ---------------------------------------------------------------------------
# GET /api/sessions/running
# ---------------------------------------------------------------------------


def test_running_returns_empty_when_no_runners(
    client_with_registry: tuple[TestClient, InProcessRunnerRegistry],
) -> None:
    client, _registry = client_with_registry
    resp = client.get("/api/sessions/running")
    assert resp.status_code == 200
    assert resp.json() == []


def test_running_returns_only_running_ids(
    client_with_registry: tuple[TestClient, InProcessRunnerRegistry],
) -> None:
    client, registry = client_with_registry
    registry._runners["ses_aaa"] = _make_runner_stub(is_running=True, is_awaiting_user=False)
    registry._runners["ses_bbb"] = _make_runner_stub(is_running=False, is_awaiting_user=False)
    registry._runners["ses_ccc"] = _make_runner_stub(is_running=True, is_awaiting_user=True)

    resp = client.get("/api/sessions/running")
    assert resp.status_code == 200
    ids = set(resp.json())
    assert ids == {"ses_aaa", "ses_ccc"}
    assert "ses_bbb" not in ids


def test_running_returns_empty_when_no_registry() -> None:
    """No runner_factory on app.state → returns [] gracefully."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/sessions/running")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/sessions/awaiting
# ---------------------------------------------------------------------------


def test_awaiting_returns_empty_when_no_runners(
    client_with_registry: tuple[TestClient, InProcessRunnerRegistry],
) -> None:
    client, _registry = client_with_registry
    resp = client.get("/api/sessions/awaiting")
    assert resp.status_code == 200
    assert resp.json() == []


def test_awaiting_returns_only_awaiting_ids(
    client_with_registry: tuple[TestClient, InProcessRunnerRegistry],
) -> None:
    client, registry = client_with_registry
    registry._runners["ses_x"] = _make_runner_stub(is_running=False, is_awaiting_user=True)
    registry._runners["ses_y"] = _make_runner_stub(is_running=True, is_awaiting_user=False)
    registry._runners["ses_z"] = _make_runner_stub(is_running=False, is_awaiting_user=False)

    resp = client.get("/api/sessions/awaiting")
    assert resp.status_code == 200
    ids = set(resp.json())
    assert ids == {"ses_x"}
    assert "ses_y" not in ids
    assert "ses_z" not in ids


def test_awaiting_returns_empty_when_no_registry() -> None:
    """No runner_factory on app.state → returns [] gracefully."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/sessions/awaiting")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# InProcessRunnerRegistry.list_running_ids / list_awaiting_ids unit tests
# ---------------------------------------------------------------------------


def test_list_running_ids_unit() -> None:
    registry = InProcessRunnerRegistry()
    registry._runners["a"] = _make_runner_stub(is_running=True, is_awaiting_user=False)
    registry._runners["b"] = _make_runner_stub(is_running=False, is_awaiting_user=True)
    assert registry.list_running_ids() == ["a"]


def test_list_awaiting_ids_unit() -> None:
    registry = InProcessRunnerRegistry()
    registry._runners["a"] = _make_runner_stub(is_running=True, is_awaiting_user=False)
    registry._runners["b"] = _make_runner_stub(is_running=False, is_awaiting_user=True)
    assert registry.list_awaiting_ids() == ["b"]
