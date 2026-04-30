"""Analytics endpoints for the v1.0.0 dashboard's `/analytics` page.

Single GET that bundles every aggregate the page renders, in one
round-trip per page load. Per-card endpoints would multiply round-
trips without changing the freshness story — the dashboard is a
periodic snapshot, refreshed on user action, not a live stream.

`days` query param clamps the time-series buckets only; the headline
totals (sessions / tokens / cost) are all-time and don't honor it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from bearings.api.auth import require_auth
from bearings.api.models import AnalyticsSummaryOut
from bearings.db import store

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_auth)],
)


@router.get("/summary", response_model=AnalyticsSummaryOut)
async def get_analytics_summary(
    request: Request,
    days: int = Query(
        30,
        ge=1,
        le=365,
        description=(
            "Window for the sessions-by-day time series. Clamped to "
            "[1, 365]. Headline totals (sessions / tokens / cost) are "
            "all-time and don't honor this param."
        ),
    ),
) -> AnalyticsSummaryOut:
    rollup = await store.get_analytics_summary(request.app.state.db, days=days)
    return AnalyticsSummaryOut(**rollup)
