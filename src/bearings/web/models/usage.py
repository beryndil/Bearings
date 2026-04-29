# mypy: disable-error-code=explicit-any
"""Pydantic wire shapes for ``routes/usage.py`` (spec §9 usage endpoints)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class UsageByModelRow(BaseModel):
    """One row of ``GET /api/usage/by_model?period=week``.

    Per spec §8 "Quota efficiency" the by_model surface aggregates
    per-model token totals plus advisor calls + cache reads. The
    aggregation slices ``messages`` rows by their per-message routing
    columns (item 1.9 wires the writes).
    """

    model_config = ConfigDict(extra="forbid")

    model: str
    role: str  # "executor" or "advisor"
    input_tokens: int
    output_tokens: int
    advisor_calls: int
    cache_read_tokens: int
    sessions: int


class UsageByTagRow(BaseModel):
    """One row of ``GET /api/usage/by_tag?period=week``.

    Tags are the user-facing classification surface; this slice rolls
    up the per-message totals into per-tag aggregates so the inspector
    can attribute spend to a tag.
    """

    model_config = ConfigDict(extra="forbid")

    tag_id: int
    tag_name: str
    executor_input_tokens: int
    executor_output_tokens: int
    advisor_input_tokens: int
    advisor_output_tokens: int
    advisor_calls: int
    sessions: int


class OverrideRateOut(BaseModel):
    """One row of ``GET /api/usage/override_rates?days=14`` per spec §9."""

    model_config = ConfigDict(extra="forbid")

    rule_kind: str
    rule_id: int
    fired_count: int
    overridden_count: int
    rate: float
    review: bool


__all__ = ["OverrideRateOut", "UsageByModelRow", "UsageByTagRow"]
