"""Tests for `POST /sessions/{id}/suggest_titles` — auto-suggest-titles
plan (`~/.claude/plans/auto-suggesting-titles.md`).

Covers:
- 404 when the session doesn't exist.
- 400 when the session is not chat-kind.
- 503 when `enable_llm_title_suggest=False` (the shipping default).
- 200 happy path with a monkeypatched SDK driver.
- 503 when the suggester fails after retries.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from bearings.config import Settings


def _default_tag(client: TestClient) -> int:
    existing = client.get("/api/tags").json()
    if existing:
        tag_id: int = existing[0]["id"]
        return tag_id
    created = client.post("/api/tags", json={"name": "default"})
    return int(created.json()["id"])


def _create(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    tag_ids = kwargs.pop("tag_ids", None) or [_default_tag(client)]
    body = {
        "working_dir": "/tmp",
        "model": "claude-sonnet-4-6",
        "title": "test session",
        "tag_ids": tag_ids,
        **kwargs,
    }
    resp = client.post("/api/sessions", json=body)
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


# ---------- validation branches -------------------------------------


def test_suggest_titles_404_on_missing_session(client: TestClient) -> None:
    resp = client.post("/api/sessions/ghost/suggest_titles")
    assert resp.status_code == 404


def test_suggest_titles_rejects_checklist_kind(client: TestClient) -> None:
    resp = client.post(
        "/api/sessions",
        json={
            "working_dir": "/tmp",
            "model": "claude-sonnet-4-6",
            "title": "checklist",
            "tag_ids": [_default_tag(client)],
            "kind": "checklist",
        },
    )
    assert resp.status_code == 200, resp.text
    sid = resp.json()["id"]
    resp = client.post(f"/api/sessions/{sid}/suggest_titles")
    assert resp.status_code == 400
    assert "chat" in resp.json()["detail"]


# ---------- config gate ---------------------------------------------


def test_suggest_titles_disabled_in_config_returns_503(
    client: TestClient, tmp_settings: Settings
) -> None:
    """`enable_llm_title_suggest=False` (the shipping default) → 503
    with a hint pointing the user at the config key."""
    src = _create(client, title="src")
    resp = client.post(f"/api/sessions/{src['id']}/suggest_titles")
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert "enable_llm_title_suggest" in detail


# ---------- enabled happy / failure paths ---------------------------


def test_suggest_titles_happy_path(
    client: TestClient, tmp_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = _create(client, title="src")
    client.app.state.settings.agent.enable_llm_title_suggest = True  # type: ignore[attr-defined]

    fake_response = '{"titles": ["Narrow take", "Medium take", "Wide take"]}'

    import bearings.agent.title_suggester as suggester_module

    real_run = suggester_module._run_query

    async def patched_run(messages: list[dict[str, Any]], **kwargs: Any) -> str:
        return fake_response

    monkeypatch.setattr(suggester_module, "_run_query", patched_run)

    try:
        resp = client.post(f"/api/sessions/{src['id']}/suggest_titles")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["titles"] == ["Narrow take", "Medium take", "Wide take"]
    finally:
        monkeypatch.setattr(suggester_module, "_run_query", real_run)
        client.app.state.settings.agent.enable_llm_title_suggest = False  # type: ignore[attr-defined]


def test_suggest_titles_503_when_query_fails(
    client: TestClient, tmp_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM enabled but every retry fails → 503 with the reason
    string. The route never falls through to a heuristic since
    title-suggest has no deterministic fallback (unlike reorg-analyze)."""
    src = _create(client, title="src")
    client.app.state.settings.agent.enable_llm_title_suggest = True  # type: ignore[attr-defined]

    import bearings.agent.title_suggester as suggester_module

    real_run = suggester_module._run_query

    async def boom(_messages: list[dict[str, Any]], **kwargs: Any) -> str:
        raise RuntimeError("transient SDK failure")

    monkeypatch.setattr(suggester_module, "_run_query", boom)

    try:
        resp = client.post(f"/api/sessions/{src['id']}/suggest_titles")
        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert detail  # non-empty reason surfaced to the UI
    finally:
        monkeypatch.setattr(suggester_module, "_run_query", real_run)
        client.app.state.settings.agent.enable_llm_title_suggest = False  # type: ignore[attr-defined]
