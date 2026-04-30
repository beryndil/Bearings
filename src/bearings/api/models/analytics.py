"""Analytics DTOs for the v1.0.0 dashboard's `/analytics` page.

A single response model bundles every aggregate the page renders so
the frontend can paint the whole surface from one fetch. Per-card
endpoints would multiply round-trips without changing freshness:
the dashboard reads at-rest, refreshing on user action, not as a
live stream.
"""

from __future__ import annotations

from pydantic import BaseModel


class SessionsByDay(BaseModel):
    """One bucket of the sessions-by-day time series. Days with zero
    sessions are zero-filled server-side so the chart axis stays
    continuous (a sparse list reads as 'no data' rather than 'no
    sessions that day')."""

    day: str  # ISO date 'YYYY-MM-DD'
    count: int


class TopTag(BaseModel):
    """One row of the top-N-tags-by-session-count list."""

    id: int
    name: str
    color: str | None = None
    session_count: int


class AnalyticsSummaryOut(BaseModel):
    """Per-instance aggregate snapshot. Counts are non-negative;
    `total_cost_usd` is a float (post-COALESCE, never null)."""

    total_sessions: int
    open_sessions: int
    closed_sessions: int

    total_messages: int

    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_creation_tokens: int
    total_tokens: int

    total_cost_usd: float

    sessions_by_day: list[SessionsByDay]
    top_tags: list[TopTag]
