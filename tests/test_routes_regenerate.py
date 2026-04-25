"""HTTP surface for Phase 15 of docs/context-menu-plan.md.

Covers the single endpoint `POST /api/sessions/{id}/regenerate_from/{message_id}`.

Decision §8.4 — fork-only semantics:
  - new session inherits parent's tags + permission_mode + model
  - title prefixed with `↳ regen: `
  - messages [1..boundary-1] copied, boundary user message itself
    excluded (the frontend re-issues it as the first prompt)
  - source session is untouched
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def _default_tag(client: TestClient) -> int:
    existing = client.get("/api/tags").json()
    if existing:
        tag_id: int = existing[0]["id"]
        return tag_id
    created = client.post("/api/tags", json={"name": "default"})
    return int(created.json()["id"])


def _seed(
    client: TestClient,
    *,
    title: str = "parent",
    permission_mode: str | None = None,
) -> dict[str, Any]:
    """Plant a session with the canonical user/assistant/user/assistant
    pattern and return the imported row plus its message list."""
    payload = {
        "session": {
            "working_dir": "/tmp",
            "model": "claude-sonnet-4-6",
            "title": title,
        },
        "messages": [
            {"id": "u1", "role": "user", "content": "alpha", "created_at": "2026-04-22T00:00:01Z"},
            {
                "id": "a1",
                "role": "assistant",
                "content": "alpha-resp",
                "created_at": "2026-04-22T00:00:02Z",
            },
            {"id": "u2", "role": "user", "content": "bravo", "created_at": "2026-04-22T00:00:03Z"},
            {
                "id": "a2",
                "role": "assistant",
                "content": "bravo-resp",
                "created_at": "2026-04-22T00:00:04Z",
            },
        ],
        "tool_calls": [],
    }
    resp = client.post("/api/sessions/import", json=payload)
    assert resp.status_code == 200, resp.text
    session = resp.json()
    if permission_mode is not None:
        # No PATCH route exposes permission_mode (it's set via the
        # `set_permission_mode` WS message in normal use). Reach into
        # the test app's DB directly and stamp the column so the
        # inheritance assertion has something to inherit.
        import asyncio

        from bearings.db import store as _store

        # The TestClient holds a reference to the FastAPI app via its
        # ASGI handler — pull the live conn off the app state.
        conn = client.app.state.db  # type: ignore[attr-defined]

        async def _stamp() -> None:
            await _store.set_session_permission_mode(conn, session["id"], permission_mode)

        asyncio.new_event_loop().run_until_complete(_stamp())
        session = client.get(f"/api/sessions/{session['id']}").json()
    messages = client.get(f"/api/sessions/{session['id']}/messages").json()
    session["_messages"] = messages
    return session


def _by_content(messages: list[dict[str, Any]], content: str) -> dict[str, Any]:
    for m in messages:
        if m["content"] == content:
            return m
    raise AssertionError(f"no message with content={content!r}")


def test_regenerate_from_assistant_walks_back_to_user_boundary(
    client: TestClient,
) -> None:
    """Targeting the second assistant message walks back to `bravo`
    as the boundary; the new session keeps `[alpha, alpha-resp]` only."""
    session = _seed(client)
    a2 = _by_content(session["_messages"], "bravo-resp")

    resp = client.post(f"/api/sessions/{session['id']}/regenerate_from/{a2['id']}")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["prompt"] == "bravo"
    new_session = body["session"]
    assert new_session["id"] != session["id"]
    assert new_session["title"].startswith("↳ regen: ")

    # New session carries only [alpha, alpha-resp] — boundary excluded.
    new_msgs = client.get(f"/api/sessions/{new_session['id']}/messages").json()
    contents = [m["content"] for m in new_msgs]
    assert contents == ["alpha", "alpha-resp"]


def test_regenerate_from_user_uses_self_as_boundary(client: TestClient) -> None:
    """Targeting a user message uses that row as the boundary; the new
    session carries everything strictly before it."""
    session = _seed(client)
    u2 = _by_content(session["_messages"], "bravo")

    resp = client.post(f"/api/sessions/{session['id']}/regenerate_from/{u2['id']}")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["prompt"] == "bravo"

    new_msgs = client.get(f"/api/sessions/{body['session']['id']}/messages").json()
    assert [m["content"] for m in new_msgs] == ["alpha", "alpha-resp"]


def test_regenerate_does_not_touch_source(client: TestClient) -> None:
    session = _seed(client)
    a2 = _by_content(session["_messages"], "bravo-resp")
    client.post(f"/api/sessions/{session['id']}/regenerate_from/{a2['id']}")
    # Source still has all four messages.
    src_msgs = client.get(f"/api/sessions/{session['id']}/messages").json()
    assert len(src_msgs) == 4


def test_regenerate_inherits_permission_mode(client: TestClient) -> None:
    session = _seed(client, permission_mode="acceptEdits")
    a2 = _by_content(session["_messages"], "bravo-resp")
    resp = client.post(f"/api/sessions/{session['id']}/regenerate_from/{a2['id']}")
    assert resp.status_code == 201
    new_session = resp.json()["session"]
    assert new_session["permission_mode"] == "acceptEdits"


def test_regenerate_unknown_message_404(client: TestClient) -> None:
    session = _seed(client)
    resp = client.post(f"/api/sessions/{session['id']}/regenerate_from/no-such-msg")
    assert resp.status_code == 404


def test_regenerate_cross_session_message_400(client: TestClient) -> None:
    """A message id from a different session is a client bug — 400 rather
    than silently regenerating into the wrong tree."""
    session_a = _seed(client, title="a")
    session_b = _seed(client, title="b")
    foreign = session_b["_messages"][0]
    resp = client.post(f"/api/sessions/{session_a['id']}/regenerate_from/{foreign['id']}")
    assert resp.status_code == 400


def test_regenerate_assistant_only_prefix_400(client: TestClient) -> None:
    """No user-turn at-or-before the target → 400 (UI gates the same
    condition with a disabled tooltip but the server enforces too)."""
    payload = {
        "session": {
            "working_dir": "/tmp",
            "model": "claude-sonnet-4-6",
            "title": "assistant-only",
        },
        "messages": [
            {
                "id": "a-solo",
                "role": "assistant",
                "content": "solo",
                "created_at": "2026-04-22T00:00:01Z",
            }
        ],
        "tool_calls": [],
    }
    resp = client.post("/api/sessions/import", json=payload)
    session = resp.json()
    msgs = client.get(f"/api/sessions/{session['id']}/messages").json()
    target = msgs[0]
    bad = client.post(f"/api/sessions/{session['id']}/regenerate_from/{target['id']}")
    assert bad.status_code == 400
