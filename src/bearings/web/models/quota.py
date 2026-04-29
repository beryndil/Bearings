# mypy: disable-error-code=explicit-any
"""Pydantic wire shapes for ``routes/quota.py`` (spec §9 quota endpoints)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class QuotaSnapshotOut(BaseModel):
    """Response body for ``GET /api/quota/current`` + ``POST /refresh``.

    Mirrors :class:`bearings.agent.quota.QuotaSnapshot`. ``raw_payload``
    is exposed as a string (the JSON the upstream returned) so the
    frontend can opportunistically parse forward-compat fields without
    Bearings having to schema them.
    """

    model_config = ConfigDict(extra="forbid")

    captured_at: int
    overall_used_pct: float | None
    sonnet_used_pct: float | None
    overall_resets_at: int | None
    sonnet_resets_at: int | None
    raw_payload: str


__all__ = ["QuotaSnapshotOut"]
