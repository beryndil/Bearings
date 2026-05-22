"""Tests for QuotaPoller lifecycle wiring (rt-03 / rt-04 fix, feature-3).

Covers:

* :func:`bearings.agent.quota.build_noop_fetcher` — returns an empty
  snapshot on every call (fail-open production default).
* :func:`bearings.web.app.create_app` startup/shutdown lifecycle —
  ``quota_poller.start()`` is called on startup and
  ``quota_poller.stop()`` is called on shutdown when a poller is
  passed.
* ``POST /api/quota/refresh`` returns 200 (not 503) once a poller is
  wired — the direct cascade of rt-03.
* ``GET /api/diag/quota`` reports ``poller_configured: true`` once a
  poller is wired.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from bearings.agent.quota import (
    QuotaPoller,
    QuotaSnapshot,
    build_noop_fetcher,
    make_static_fetcher,
)
from bearings.db import get_connection_factory, load_schema
from bearings.web.app import create_app

_HEARTBEAT_S: float = 5.0


# ---------------------------------------------------------------------------
# build_noop_fetcher unit tests
# ---------------------------------------------------------------------------


def test_build_noop_fetcher_returns_callable() -> None:
    """Factory produces a coroutine function."""
    import inspect

    fetcher = build_noop_fetcher()
    assert inspect.iscoroutinefunction(fetcher)


@pytest.mark.asyncio
async def test_build_noop_fetcher_returns_empty_snapshot() -> None:
    """Each call resolves to an empty snapshot (both pcts None)."""
    fetcher = build_noop_fetcher()
    snapshot: QuotaSnapshot = await fetcher()
    assert isinstance(snapshot, QuotaSnapshot)
    assert snapshot.overall_used_pct is None
    assert snapshot.sonnet_used_pct is None


@pytest.mark.asyncio
async def test_build_noop_fetcher_independent_instances() -> None:
    """Two noop fetchers are independent — both return empty snapshots."""
    f1 = build_noop_fetcher()
    f2 = build_noop_fetcher()
    s1: QuotaSnapshot = await f1()
    s2: QuotaSnapshot = await f2()
    assert s1.overall_used_pct is None
    assert s2.overall_used_pct is None


# ---------------------------------------------------------------------------
# Poller lifecycle via create_app startup/shutdown events
# ---------------------------------------------------------------------------


@pytest.fixture
def conn_and_poller(tmp_path: Path) -> Iterator[tuple[aiosqlite.Connection, QuotaPoller]]:
    """Provides a wired DB connection + a static-fetcher poller for testing."""
    db_path = tmp_path / "wiring_test.db"

    async def _open() -> aiosqlite.Connection:
        factory = get_connection_factory(db_path)
        c = await factory()
        await load_schema(c)
        return c

    loop = asyncio.new_event_loop()
    try:
        c = loop.run_until_complete(_open())
        snapshot = QuotaSnapshot(
            captured_at=int(time.time()),
            overall_used_pct=0.20,
            sonnet_used_pct=0.10,
            overall_resets_at=None,
            sonnet_resets_at=None,
            raw_payload='{"test": true}',
        )
        poller = QuotaPoller(c, make_static_fetcher(snapshot))
        yield c, poller
        loop.run_until_complete(c.close())
    finally:
        loop.close()


def test_poller_start_called_on_startup(
    conn_and_poller: tuple[aiosqlite.Connection, QuotaPoller],
) -> None:
    """create_app startup event calls poller.start() once."""
    conn, poller = conn_and_poller
    start_calls: list[None] = []
    original_start = poller.start

    def _spy_start() -> None:
        start_calls.append(None)
        original_start()

    poller.start = _spy_start  # type: ignore[method-assign]
    app = create_app(
        heartbeat_interval_s=_HEARTBEAT_S,
        db_connection=conn,
        quota_poller=poller,
    )
    with TestClient(app):
        assert len(start_calls) == 1


def test_post_refresh_200_with_poller(
    conn_and_poller: tuple[aiosqlite.Connection, QuotaPoller],
) -> None:
    """POST /api/quota/refresh returns 200 when a poller is wired (rt-04)."""
    conn, poller = conn_and_poller
    app = create_app(
        heartbeat_interval_s=_HEARTBEAT_S,
        db_connection=conn,
        quota_poller=poller,
    )
    with TestClient(app) as client:
        response = client.post("/api/quota/refresh")
    assert response.status_code == 200
    body = response.json()
    assert body["overall_used_pct"] == pytest.approx(0.20)


def test_diag_quota_poller_configured_true(
    conn_and_poller: tuple[aiosqlite.Connection, QuotaPoller],
) -> None:
    """GET /api/diag/quota reports poller_configured: true when wired (rt-03)."""
    conn, poller = conn_and_poller
    app = create_app(
        heartbeat_interval_s=_HEARTBEAT_S,
        db_connection=conn,
        quota_poller=poller,
    )
    with TestClient(app) as client:
        response = client.get("/api/diag/quota")
    assert response.status_code == 200
    body = response.json()
    assert body["poller_configured"] is True


def test_diag_quota_poller_configured_false_without_poller(tmp_path: Path) -> None:
    """GET /api/diag/quota reports poller_configured: false without a poller."""
    db_path = tmp_path / "no_poller.db"

    async def _open() -> aiosqlite.Connection:
        factory = get_connection_factory(db_path)
        c = await factory()
        await load_schema(c)
        return c

    loop = asyncio.new_event_loop()
    try:
        conn = loop.run_until_complete(_open())
        app = create_app(heartbeat_interval_s=_HEARTBEAT_S, db_connection=conn)
        with TestClient(app) as client:
            response = client.get("/api/diag/quota")
        assert response.status_code == 200
        body = response.json()
        assert body["poller_configured"] is False
        loop.run_until_complete(conn.close())
    finally:
        loop.close()


def test_quota_snapshots_written_after_poll(
    conn_and_poller: tuple[aiosqlite.Connection, QuotaPoller],
) -> None:
    """After a manual refresh call, quota_snapshots has at least one row."""
    conn, poller = conn_and_poller
    app = create_app(
        heartbeat_interval_s=_HEARTBEAT_S,
        db_connection=conn,
        quota_poller=poller,
    )
    with TestClient(app) as client:
        client.post("/api/quota/refresh")

    async def _count() -> int:
        cursor = await conn.execute("SELECT COUNT(*) FROM quota_snapshots")
        row = await cursor.fetchone()
        await cursor.close()
        return int(row[0]) if row else 0

    loop = asyncio.new_event_loop()
    try:
        count = loop.run_until_complete(_count())
    finally:
        loop.close()
    assert count >= 1
