from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _fake_home(
    monkeypatch: pytest.MonkeyPatch,
    home: Path,
) -> None:
    """Route reads from `Path.home()`. Fake it so the test doesn't
    depend on the developer's real ~/.claude tree."""
    monkeypatch.setattr("bearings.api.routes_commands.Path.home", lambda: home)


def test_list_returns_empty_when_no_dotclaude(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_home(monkeypatch, tmp_path / "empty")
    (tmp_path / "empty").mkdir()
    resp = client.get("/api/commands")
    assert resp.status_code == 200
    assert resp.json() == {"entries": []}


def test_list_returns_user_commands(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    _write(home / ".claude/commands/review.md", "---\ndescription: Review PR\n---\nbody")
    _fake_home(monkeypatch, home)

    resp = client.get("/api/commands")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["entries"]) == 1
    entry = body["entries"][0]
    assert entry["slug"] == "review"
    assert entry["description"] == "Review PR"
    assert entry["kind"] == "command"
    assert entry["scope"] == "user"


def test_list_includes_project_scope(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "proj"
    _write(home / ".claude/commands/user-only.md", "body")
    _write(project / ".claude/commands/proj-only.md", "---\ndescription: project cmd\n---\n")
    _fake_home(monkeypatch, home)

    resp = client.get("/api/commands", params={"cwd": str(project)})
    assert resp.status_code == 200
    slugs = sorted(e["slug"] for e in resp.json()["entries"])
    assert slugs == ["proj-only", "user-only"]
    proj = next(e for e in resp.json()["entries"] if e["slug"] == "proj-only")
    assert proj["scope"] == "project"


def test_list_rejects_relative_cwd(client: TestClient) -> None:
    resp = client.get("/api/commands", params={"cwd": "./relative"})
    assert resp.status_code == 400
    assert "absolute" in resp.json()["detail"]


def test_list_ignores_missing_cwd_silently(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A session outliving its project directory shouldn't crash the
    palette — user/plugin entries still come through."""
    home = tmp_path / "home"
    _write(home / ".claude/commands/x.md", "body")
    _fake_home(monkeypatch, home)

    resp = client.get("/api/commands", params={"cwd": str(tmp_path / "nope")})
    assert resp.status_code == 200
    assert [e["slug"] for e in resp.json()["entries"]] == ["x"]
