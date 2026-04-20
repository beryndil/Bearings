from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_list_returns_subdirs_sorted(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "Zeta").mkdir()
    (tmp_path / "alpha").mkdir()
    (tmp_path / "mike").mkdir()
    (tmp_path / "a-file.txt").write_text("not a dir")

    resp = client.get("/api/fs/list", params={"path": str(tmp_path)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["path"] == str(tmp_path)
    assert body["parent"] == str(tmp_path.parent)
    # Case-insensitive alphabetical; files excluded.
    assert [e["name"] for e in body["entries"]] == ["alpha", "mike", "Zeta"]
    assert all(e["path"].startswith(str(tmp_path)) for e in body["entries"])


def test_list_omits_hidden_by_default(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "src").mkdir()
    resp = client.get("/api/fs/list", params={"path": str(tmp_path)})
    names = [e["name"] for e in resp.json()["entries"]]
    assert names == ["src"]


def test_list_includes_hidden_when_requested(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "src").mkdir()
    resp = client.get("/api/fs/list", params={"path": str(tmp_path), "hidden": "true"})
    names = [e["name"] for e in resp.json()["entries"]]
    assert names == [".git", "src"]


def test_list_rejects_relative_path(client: TestClient) -> None:
    resp = client.get("/api/fs/list", params={"path": "./relative"})
    assert resp.status_code == 400
    assert "absolute" in resp.json()["detail"]


def test_list_404s_on_missing_path(client: TestClient, tmp_path: Path) -> None:
    resp = client.get("/api/fs/list", params={"path": str(tmp_path / "nope")})
    assert resp.status_code == 404


def test_list_404s_on_file_path(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("")
    resp = client.get("/api/fs/list", params={"path": str(target)})
    assert resp.status_code == 404


def test_list_defaults_to_home(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no `path` query param, lists `$HOME`. Uses tmp_path as a
    fake home so tests don't depend on the developer's real home
    contents."""
    (tmp_path / "ProjectA").mkdir()
    monkeypatch.setattr("twrminal.api.routes_fs.Path.home", lambda: tmp_path)
    resp = client.get("/api/fs/list")
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == str(tmp_path)
    assert "ProjectA" in [e["name"] for e in body["entries"]]


def test_list_root_parent_is_null(client: TestClient) -> None:
    """`/` has no parent — the UI uses this to hide the ⬆ button."""
    resp = client.get("/api/fs/list", params={"path": "/"})
    assert resp.status_code == 200
    assert resp.json()["parent"] is None
