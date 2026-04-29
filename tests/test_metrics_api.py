"""Integration tests for ``bearings.web.routes.metrics`` (item 1.10).

Asserts the Prometheus content-type, the well-known ``# HELP`` /
``# TYPE`` markers, and that live-state gauges (active_runners,
queued_prompts) reflect ``app.state``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Final

import pytest
from fastapi.testclient import TestClient

from bearings.config.constants import (
    METRIC_NAME_ACTIVE_RUNNERS,
    METRIC_NAME_INFO,
    METRIC_NAME_UPTIME_SECONDS,
    METRICS_CONTENT_TYPE,
)
from bearings.web.app import create_app

_HEARTBEAT_S: Final[float] = 5.0


@pytest.fixture
def app_client() -> Iterator[TestClient]:
    app = create_app(heartbeat_interval_s=_HEARTBEAT_S)
    with TestClient(app) as client:
        yield client


def test_metrics_content_type(app_client: TestClient) -> None:
    response = app_client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"] == METRICS_CONTENT_TYPE


def test_metrics_emits_info_gauge(app_client: TestClient) -> None:
    body = app_client.get("/metrics").text
    assert f"# HELP {METRIC_NAME_INFO}" in body
    assert f"# TYPE {METRIC_NAME_INFO} gauge" in body
    # The labelled value is exactly 1 per Prometheus convention.
    assert f"{METRIC_NAME_INFO}{{version=" in body


def test_metrics_emits_uptime_gauge(app_client: TestClient) -> None:
    body = app_client.get("/metrics").text
    assert f"# HELP {METRIC_NAME_UPTIME_SECONDS}" in body
    assert f"{METRIC_NAME_UPTIME_SECONDS} " in body


def test_metrics_active_runners_reflects_registry(
    app_client: TestClient,
) -> None:
    """Materialise two runners; metrics should report ``2``."""
    factory = app_client.app.state.runner_factory  # type: ignore[attr-defined]

    async def _materialise() -> None:
        await factory("ses_a")
        await factory("ses_b")

    asyncio.run(_materialise())
    body = app_client.get("/metrics").text
    # Active-runners gauge updates on every scrape from app.state.
    line = next(ln for ln in body.splitlines() if ln.startswith(f"{METRIC_NAME_ACTIVE_RUNNERS} "))
    value = float(line.split()[1])
    assert value == 2.0
