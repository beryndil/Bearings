"""Tests for GET /api/version (N-14 — bundle mtime endpoint)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from bearings.web.app import create_app
from bearings.web.routes.version import _bundle_mtime


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_get_version_returns_200(client: TestClient) -> None:
    resp = client.get("/api/version")
    assert resp.status_code == 200
    body = resp.json()
    assert "bundle_mtime" in body
    assert isinstance(body["bundle_mtime"], float)


def test_bundle_mtime_zero_when_dir_missing(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does_not_exist"
    with patch("bearings.web.routes.version._DIST_DIR", nonexistent):
        assert _bundle_mtime() == 0.0


def test_bundle_mtime_zero_when_dir_empty(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    with patch("bearings.web.routes.version._DIST_DIR", dist):
        assert _bundle_mtime() == 0.0


def test_bundle_mtime_returns_mtime_of_newest_file(tmp_path: Path) -> None:
    import os
    import time

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "a.js").write_text("a")
    time.sleep(0.05)
    (dist / "b.css").write_text("b")

    with patch("bearings.web.routes.version._DIST_DIR", dist):
        mtime = _bundle_mtime()

    b_mtime = os.path.getmtime(dist / "b.css")
    # Should return the mtime of the newest file (b.css)
    assert abs(mtime - b_mtime) < 0.01
