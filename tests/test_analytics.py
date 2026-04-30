"""Tests for the v1.0.0 dashboard's `/api/analytics/summary` endpoint
and the underlying `db.get_analytics_summary()` aggregator."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bearings.db.store import (
    create_session,
    get_analytics_summary,
    init_db,
    insert_message,
)


@pytest.mark.asyncio
async def test_analytics_summary_empty_db(tmp_path: Path) -> None:
    """Empty database → all zeros, never None."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        rollup = await get_analytics_summary(conn)
        assert rollup["total_sessions"] == 0
        assert rollup["open_sessions"] == 0
        assert rollup["closed_sessions"] == 0
        assert rollup["total_messages"] == 0
        assert rollup["total_input_tokens"] == 0
        assert rollup["total_output_tokens"] == 0
        assert rollup["total_cache_read_tokens"] == 0
        assert rollup["total_cache_creation_tokens"] == 0
        assert rollup["total_tokens"] == 0
        assert rollup["total_cost_usd"] == 0.0
        # `top_tags` may carry the migration-seeded severity tags
        # (Blocker / Critical / Medium / Low / QoL) — every fresh DB
        # has them, all with session_count=0.
        assert all(t["session_count"] == 0 for t in rollup["top_tags"])
        # Sessions-by-day is zero-filled for the full window.
        assert len(rollup["sessions_by_day"]) == 30
        assert all(b["count"] == 0 for b in rollup["sessions_by_day"])
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_analytics_summary_counts_sessions_and_tokens(tmp_path: Path) -> None:
    """Aggregates fold across multiple sessions / messages correctly."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        s1 = await create_session(conn, working_dir=str(tmp_path), model="m")
        s2 = await create_session(conn, working_dir=str(tmp_path), model="m")
        await insert_message(
            conn,
            session_id=s1["id"],
            role="user",
            content="hi",
            input_tokens=10,
            output_tokens=20,
            cache_read_tokens=5,
            cache_creation_tokens=2,
        )
        await insert_message(
            conn,
            session_id=s2["id"],
            role="assistant",
            content="hey",
            input_tokens=3,
            output_tokens=4,
        )
        rollup = await get_analytics_summary(conn)
        assert rollup["total_sessions"] == 2
        assert rollup["open_sessions"] == 2
        assert rollup["closed_sessions"] == 0
        assert rollup["total_messages"] == 2
        assert rollup["total_input_tokens"] == 13
        assert rollup["total_output_tokens"] == 24
        assert rollup["total_cache_read_tokens"] == 5
        assert rollup["total_cache_creation_tokens"] == 2
        assert rollup["total_tokens"] == 13 + 24 + 5 + 2
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_analytics_top_tags_sorted_by_session_count(tmp_path: Path) -> None:
    """Top-tags list is ordered by session_count desc (then name).
    A tag with no sessions still surfaces (LEFT JOIN), with count 0."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        # Use put_tag_memory just to seed tags (it creates none); use the
        # raw create_tag instead.
        from bearings.db.store import attach_tag, create_tag

        big = await create_tag(conn, name="big")
        small = await create_tag(conn, name="small")
        # `lonely` carries no sessions; should still appear with 0.
        await create_tag(conn, name="lonely")
        s1 = await create_session(conn, working_dir=str(tmp_path), model="m")
        s2 = await create_session(conn, working_dir=str(tmp_path), model="m")
        s3 = await create_session(conn, working_dir=str(tmp_path), model="m")
        await attach_tag(conn, s1["id"], big["id"])
        await attach_tag(conn, s2["id"], big["id"])
        await attach_tag(conn, s3["id"], big["id"])
        await attach_tag(conn, s1["id"], small["id"])

        rollup = await get_analytics_summary(conn)
        names_in_order = [t["name"] for t in rollup["top_tags"]]
        # `big` is most popular, `small` next, `lonely` last (with 0).
        assert names_in_order[0] == "big"
        assert names_in_order[1] == "small"
        assert "lonely" in names_in_order
        # Counts match the inserts.
        by_name = {t["name"]: t["session_count"] for t in rollup["top_tags"]}
        assert by_name["big"] == 3
        assert by_name["small"] == 1
        assert by_name["lonely"] == 0
    finally:
        await conn.close()


def test_analytics_summary_endpoint_smoke(client: TestClient) -> None:
    """End-to-end: hits the FastAPI route, returns the documented shape."""
    resp = client.get("/api/analytics/summary")
    assert resp.status_code == 200
    body = resp.json()
    required = {
        "total_sessions",
        "open_sessions",
        "closed_sessions",
        "total_messages",
        "total_input_tokens",
        "total_output_tokens",
        "total_cache_read_tokens",
        "total_cache_creation_tokens",
        "total_tokens",
        "total_cost_usd",
        "sessions_by_day",
        "top_tags",
    }
    assert required <= body.keys()
    assert isinstance(body["sessions_by_day"], list)
    assert isinstance(body["top_tags"], list)


def test_analytics_summary_endpoint_window_param(client: TestClient) -> None:
    """`days` query param bounds the time-series length."""
    resp = client.get("/api/analytics/summary?days=7")
    assert resp.status_code == 200
    assert len(resp.json()["sessions_by_day"]) == 7

    # Too-small or too-large values are 422'd by the Query validator.
    assert client.get("/api/analytics/summary?days=0").status_code == 422
    assert client.get("/api/analytics/summary?days=400").status_code == 422
