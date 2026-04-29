"""Integration tests for the messages API endpoints (item 1.9).

Covers ``GET /api/sessions/{session_id}/messages`` (list) and
``GET /api/messages/{message_id}`` (single fetch). The list endpoint
returns rows oldest-first; single fetch 404s on a missing id; both
return the spec §5 routing/usage columns + the spec §App A
``matched_rule_id`` projection.

The list endpoint also accepts a ``limit`` query parameter that
returns the *tail* of the transcript (most recent N rows), matching
the underlying :func:`bearings.db.messages.list_for_session` shape.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bearings.agent.persistence import persist_assistant_turn
from bearings.agent.routing import RoutingDecision
from bearings.config.constants import (
    MESSAGES_LIST_MAX_LIMIT,
    SESSION_KIND_CHAT,
)
from bearings.db import messages as messages_db
from bearings.db import sessions as sessions_db
from bearings.db.connection import load_schema
from bearings.web.app import create_app


@pytest.fixture
async def app_and_db(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, aiosqlite.Connection]]:
    db_path = tmp_path / "msgapi.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        app = create_app(db_connection=conn)
        yield app, conn
    finally:
        await conn.close()


async def _new_chat(conn: aiosqlite.Connection, title: str = "t") -> str:
    s = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title=title, working_dir="/wd", model="sonnet"
    )
    return s.id


def _decision(matched_rule_id: int | None = 30) -> RoutingDecision:
    return RoutingDecision(
        executor_model="haiku",
        advisor_model="opus",
        advisor_max_uses=3,
        effort_level="low",
        source="system_rule",
        reason="Exploration — Haiku is what Anthropic auto-selects for the Explore subagent",
        matched_rule_id=matched_rule_id,
    )


async def test_list_messages_returns_404_for_missing_session(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _ = app_and_db
    with TestClient(app) as client:
        response = client.get("/api/sessions/ses_nope/messages")
    assert response.status_code == 404


async def test_list_messages_empty_session_returns_empty_array(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat(conn)
    with TestClient(app) as client:
        response = client.get(f"/api/sessions/{sid}/messages")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_messages_returns_routing_and_usage_fields(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Per spec §5 + §7 every routing/usage column surfaces on the wire."""
    app, conn = app_and_db
    sid = await _new_chat(conn)
    await messages_db.insert_user(conn, session_id=sid, content="explore the repo")
    await persist_assistant_turn(
        conn,
        session_id=sid,
        content="here is what I found",
        decision=_decision(),
        model_usage={
            "claude-haiku-4-5": {
                "input_tokens": 80,
                "output_tokens": 200,
                "cache_read_input_tokens": 50,
            },
            "claude-opus-4-6": {
                "input_tokens": 30,
                "output_tokens": 150,
                "cache_read_input_tokens": 0,
            },
        },
    )
    with TestClient(app) as client:
        response = client.get(f"/api/sessions/{sid}/messages")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    user_row, assistant_row = body
    assert user_row["role"] == "user"
    # User row leaves routing fields NULL per item 1.7 + spec §5.
    assert user_row["executor_model"] is None
    assert user_row["routing_source"] is None
    assert user_row["matched_rule_id"] is None
    # Assistant row carries the routing decision + usage projection.
    assert assistant_row["role"] == "assistant"
    assert assistant_row["executor_model"] == "haiku"
    assert assistant_row["advisor_model"] == "opus"
    assert assistant_row["effort_level"] == "low"
    assert assistant_row["routing_source"] == "system_rule"
    assert assistant_row["matched_rule_id"] == 30
    assert assistant_row["executor_input_tokens"] == 80
    assert assistant_row["executor_output_tokens"] == 200
    assert assistant_row["advisor_input_tokens"] == 30
    assert assistant_row["advisor_output_tokens"] == 150
    assert assistant_row["advisor_calls_count"] == 1
    assert assistant_row["cache_read_tokens"] == 50


async def test_list_messages_with_limit_returns_tail(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat(conn)
    await messages_db.insert_user(conn, session_id=sid, content="first")
    await messages_db.insert_user(conn, session_id=sid, content="second")
    await messages_db.insert_user(conn, session_id=sid, content="third")
    with TestClient(app) as client:
        response = client.get(f"/api/sessions/{sid}/messages", params={"limit": 2})
    assert response.status_code == 200
    contents = [row["content"] for row in response.json()]
    assert contents == ["second", "third"]


async def test_list_messages_rejects_invalid_limit(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Limit ≤ 0 and > MESSAGES_LIST_MAX_LIMIT are 422."""
    app, conn = app_and_db
    sid = await _new_chat(conn)
    with TestClient(app) as client:
        zero = client.get(f"/api/sessions/{sid}/messages", params={"limit": 0})
        too_big = client.get(
            f"/api/sessions/{sid}/messages",
            params={"limit": MESSAGES_LIST_MAX_LIMIT + 1},
        )
    assert zero.status_code == 422
    assert too_big.status_code == 422


async def test_get_message_404_for_missing_id(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, _ = app_and_db
    with TestClient(app) as client:
        response = client.get("/api/messages/msg_nope")
    assert response.status_code == 404


async def test_get_message_returns_full_routing_payload(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    app, conn = app_and_db
    sid = await _new_chat(conn)
    msg = await persist_assistant_turn(
        conn,
        session_id=sid,
        content="response",
        decision=_decision(matched_rule_id=None),
        model_usage=None,
    )
    with TestClient(app) as client:
        response = client.get(f"/api/messages/{msg.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == msg.id
    assert body["session_id"] == sid
    assert body["matched_rule_id"] is None
    assert body["executor_model"] == "haiku"
    assert body["advisor_calls_count"] == 0
