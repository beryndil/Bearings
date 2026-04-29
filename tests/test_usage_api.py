"""Integration tests for ``bearings.web.routes.usage`` (spec §9 usage)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from bearings.db import get_connection_factory, load_schema
from bearings.web.app import create_app

_HEARTBEAT_S: Final[float] = 5.0


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[TestClient]:
    db_path = tmp_path / "usage_api.db"

    async def _open() -> aiosqlite.Connection:
        factory = get_connection_factory(db_path)
        conn = await factory()
        await load_schema(conn)
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


def test_by_model_empty_db_returns_empty_list(app_client: TestClient) -> None:
    """No messages → no rows."""
    response = app_client.get("/api/usage/by_model")
    assert response.status_code == 200
    assert response.json() == []


def test_by_model_invalid_period_returns_422(app_client: TestClient) -> None:
    """Period must be in {day, week}."""
    response = app_client.get("/api/usage/by_model?period=month")
    assert response.status_code == 422


def test_by_model_aggregates_executor_and_advisor_rows(
    tmp_path: Path,
) -> None:
    """A message with both executor + advisor surfaces as two rows."""
    db_path = tmp_path / "by_model.db"

    async def _open() -> aiosqlite.Connection:
        factory = get_connection_factory(db_path)
        conn = await factory()
        await load_schema(conn)
        iso_now = time.strftime(
            "%Y-%m-%dT%H:%M:%S.000000+00:00",
            time.gmtime(time.time()),
        )
        # Seed session + one message with full per-model usage.
        await conn.execute(
            "INSERT INTO sessions (id, kind, title, working_dir, model, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("s1", "chat", "t", "/tmp", "sonnet", iso_now, iso_now),
        )
        await conn.execute(
            "INSERT INTO messages (id, session_id, role, content, "
            "executor_model, advisor_model, executor_input_tokens, "
            "executor_output_tokens, advisor_input_tokens, "
            "advisor_output_tokens, advisor_calls_count, cache_read_tokens, "
            "created_at) VALUES (?, ?, 'assistant', '', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "msg_1",
                "s1",
                "sonnet",
                "opus",
                100,
                200,
                50,
                75,
                1,
                25,
                iso_now,
            ),
        )
        await conn.commit()
        return conn

    loop = asyncio.new_event_loop()
    try:
        conn = loop.run_until_complete(_open())
        app = create_app(heartbeat_interval_s=_HEARTBEAT_S, db_connection=conn)
        with TestClient(app) as client:
            response = client.get("/api/usage/by_model?period=week")
            assert response.status_code == 200
            rows = response.json()
            # One executor row + one advisor row.
            assert len(rows) == 2
            executor_row = next(r for r in rows if r["role"] == "executor")
            advisor_row = next(r for r in rows if r["role"] == "advisor")
            assert executor_row["model"] == "sonnet"
            assert executor_row["input_tokens"] == 100
            assert advisor_row["model"] == "opus"
            assert advisor_row["input_tokens"] == 50
        loop.run_until_complete(conn.close())
    finally:
        loop.close()


def test_by_tag_empty_db_returns_empty_list(app_client: TestClient) -> None:
    """No tags → no rows."""
    response = app_client.get("/api/usage/by_tag")
    assert response.status_code == 200
    assert response.json() == []


def test_by_tag_aggregates_per_tag_totals(tmp_path: Path) -> None:
    """A tagged session's tokens aggregate under the tag."""
    db_path = tmp_path / "by_tag.db"

    async def _open() -> aiosqlite.Connection:
        factory = get_connection_factory(db_path)
        conn = await factory()
        await load_schema(conn)
        iso_now = time.strftime(
            "%Y-%m-%dT%H:%M:%S.000000+00:00",
            time.gmtime(time.time()),
        )
        await conn.execute(
            "INSERT INTO tags (id, name, color, default_model, working_dir, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, "frontend", None, None, None, iso_now, iso_now),
        )
        await conn.execute(
            "INSERT INTO sessions (id, kind, title, working_dir, model, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("s1", "chat", "t", "/tmp", "sonnet", iso_now, iso_now),
        )
        await conn.execute(
            "INSERT INTO session_tags (session_id, tag_id, created_at) VALUES (?, ?, ?)",
            ("s1", 1, iso_now),
        )
        await conn.execute(
            "INSERT INTO messages (id, session_id, role, content, "
            "executor_model, executor_input_tokens, executor_output_tokens, "
            "advisor_input_tokens, advisor_output_tokens, advisor_calls_count, "
            "created_at) VALUES (?, ?, 'assistant', '', ?, ?, ?, ?, ?, ?, ?)",
            ("msg_1", "s1", "sonnet", 100, 200, 0, 0, 0, iso_now),
        )
        await conn.commit()
        return conn

    loop = asyncio.new_event_loop()
    try:
        conn = loop.run_until_complete(_open())
        app = create_app(heartbeat_interval_s=_HEARTBEAT_S, db_connection=conn)
        with TestClient(app) as client:
            response = client.get("/api/usage/by_tag?period=week")
            assert response.status_code == 200
            rows = response.json()
            assert len(rows) == 1
            assert rows[0]["tag_name"] == "frontend"
            assert rows[0]["executor_input_tokens"] == 100
        loop.run_until_complete(conn.close())
    finally:
        loop.close()


def test_override_rates_empty_db_returns_empty_list(
    app_client: TestClient,
) -> None:
    """No messages → no rates."""
    response = app_client.get("/api/usage/override_rates")
    assert response.status_code == 200
    assert response.json() == []


def test_override_rates_rejects_invalid_days(app_client: TestClient) -> None:
    """``days`` query parameter validated."""
    response = app_client.get("/api/usage/override_rates?days=0")
    assert response.status_code == 422
