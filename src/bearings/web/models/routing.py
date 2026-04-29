# mypy: disable-error-code=explicit-any
"""Pydantic wire shapes for ``routes/routing.py`` (spec §9 routing endpoints).

Mirrors :class:`bearings.db.routing.RoutingRule` /
:class:`bearings.db.routing.SystemRoutingRule` row dataclasses. The
preview endpoint exposes a flatter shape per spec §9 (just the fields
the new-session dialog reads).

The ``mypy: disable-error-code=explicit-any`` pragma matches the
narrow carve-out :mod:`bearings.web.models.tags` makes for Pydantic's
metaclass ``Any`` surface.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RoutingRuleIn(BaseModel):
    """Request body for tag rule POST/PATCH."""

    model_config = ConfigDict(extra="forbid")

    priority: int = Field(default=100, ge=0)
    enabled: bool = True
    match_type: str
    match_value: str | None = None
    executor_model: str
    advisor_model: str | None = None
    advisor_max_uses: int = Field(default=5, ge=0)
    effort_level: str = "auto"
    reason: str = Field(min_length=1)


class SystemRoutingRuleIn(BaseModel):
    """Request body for system rule POST/PATCH."""

    model_config = ConfigDict(extra="forbid")

    priority: int = Field(default=1000, ge=0)
    enabled: bool = True
    match_type: str
    match_value: str | None = None
    executor_model: str
    advisor_model: str | None = None
    advisor_max_uses: int = Field(default=5, ge=0)
    effort_level: str = "auto"
    reason: str = Field(min_length=1)


class RoutingRuleOut(BaseModel):
    """Response body for tag rule endpoints."""

    model_config = ConfigDict(extra="forbid")

    id: int
    tag_id: int
    priority: int
    enabled: bool
    match_type: str
    match_value: str | None
    executor_model: str
    advisor_model: str | None
    advisor_max_uses: int
    effort_level: str
    reason: str
    created_at: int
    updated_at: int


class SystemRoutingRuleOut(BaseModel):
    """Response body for system rule endpoints."""

    model_config = ConfigDict(extra="forbid")

    id: int
    priority: int
    enabled: bool
    match_type: str
    match_value: str | None
    executor_model: str
    advisor_model: str | None
    advisor_max_uses: int
    effort_level: str
    reason: str
    seeded: bool
    created_at: int
    updated_at: int


class RoutingReorderIn(BaseModel):
    """Request body for ``PATCH /api/tags/{id}/routing/reorder`` (spec §9)."""

    model_config = ConfigDict(extra="forbid")

    ids_in_priority_order: list[int] = Field(min_length=0)


class RoutingPreviewIn(BaseModel):
    """Request body for ``POST /api/routing/preview`` (spec §9)."""

    model_config = ConfigDict(extra="forbid")

    tags: list[int] = Field(default_factory=list)
    message: str = ""


class RoutingPreviewOut(BaseModel):
    """Response body for ``POST /api/routing/preview`` per spec §9.

    Fields:

    * ``executor`` / ``advisor`` / ``advisor_max_uses`` / ``effort`` —
      the resolved decision after both ``evaluate()`` and
      ``apply_quota_guard()``.
    * ``source`` / ``reason`` — spec §App A enum + free-text.
    * ``matched_rule_id`` — None when the absolute default fires.
    * ``evaluated_rules`` — debug surface ("Why this model?").
    * ``quota_downgrade_applied`` — boolean per spec §9 contract:
      ``True`` when the post-guard source is ``'quota_downgrade'``.
    * ``quota_state`` — the ``{overall_used_pct, sonnet_used_pct}``
      snapshot at decision time, mirroring the per-message
      persistence path (item 1.9).
    """

    model_config = ConfigDict(extra="forbid")

    executor: str
    advisor: str | None
    advisor_max_uses: int
    effort: str
    source: str
    reason: str
    matched_rule_id: int | None
    evaluated_rules: list[int]
    quota_downgrade_applied: bool
    quota_state: dict[str, float]


__all__ = [
    "RoutingPreviewIn",
    "RoutingPreviewOut",
    "RoutingReorderIn",
    "RoutingRuleIn",
    "RoutingRuleOut",
    "SystemRoutingRuleIn",
    "SystemRoutingRuleOut",
]
