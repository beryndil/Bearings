"""Tests for GET /api/pending (N-10/R-3 — canonical pending-ops list endpoint)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from bearings.web.app import create_app

_TOML_TWO_OPS = """\
[ops.deploy]
description = "Deploy to prod"
started_at = "2024-01-01T00:00:00Z"

[ops.review]
description = "Code review"
started_at = "2024-01-02T00:00:00Z"
command = "make review"
dir = "/projects/myapp"
"""

_TOML_ONE_OP = """\
[ops.build]
description = "Build the app"
started_at = "2024-03-01T08:00:00Z"
"""


def _pending_path(project_root: Path) -> Path:
    p = project_root / ".bearings" / "pending.toml"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def test_list_pending_returns_empty_when_file_absent(tmp_path: Path) -> None:
    """Returns [] when the file does not exist (directory not onboarded)."""
    client = TestClient(create_app())
    resp = client.get("/api/pending", params={"directory": str(tmp_path)})
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_pending_returns_one_op(tmp_path: Path) -> None:
    _pending_path(tmp_path).write_text(_TOML_ONE_OP)
    client = TestClient(create_app())
    resp = client.get("/api/pending", params={"directory": str(tmp_path)})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "build"
    assert items[0]["description"] == "Build the app"
    assert items[0]["started_at"] == "2024-03-01T08:00:00Z"
    assert items[0]["command"] is None
    assert items[0]["dir"] is None


def test_list_pending_returns_two_ops_sorted_oldest_first(tmp_path: Path) -> None:
    _pending_path(tmp_path).write_text(_TOML_TWO_OPS)
    client = TestClient(create_app())
    resp = client.get("/api/pending", params={"directory": str(tmp_path)})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    # sorted oldest-first by started_at
    assert items[0]["name"] == "deploy"
    assert items[1]["name"] == "review"
    assert items[1]["command"] == "make review"
    assert items[1]["dir"] == "/projects/myapp"


def test_list_pending_returns_422_without_directory() -> None:
    """directory query param is required."""
    client = TestClient(create_app())
    resp = client.get("/api/pending")
    assert resp.status_code == 422


def test_list_pending_empty_toml_table(tmp_path: Path) -> None:
    """An empty [ops] table returns []."""
    _pending_path(tmp_path).write_text("")
    client = TestClient(create_app())
    resp = client.get("/api/pending", params={"directory": str(tmp_path)})
    assert resp.status_code == 200
    assert resp.json() == []
