# mypy: disable-error-code=explicit-any
"""Pydantic wire shapes for ``routes/checklists.py``.

Per ``docs/architecture-v1.md`` §1.1.5 the wire DTOs live alongside
the route module. The shapes mirror :class:`bearings.db.checklists.ChecklistItem`
+ :class:`bearings.db.checklists.PairedChatLeg` +
:class:`bearings.db.auto_driver_runs.AutoDriverRun` row dataclasses.

The ``mypy: disable-error-code=explicit-any`` pragma matches the same
narrow carve-out :mod:`bearings.web.models.tags` makes for Pydantic's
metaclass-exposed ``Any`` surface.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from bearings.config.constants import (
    AUTO_DRIVER_FAILURE_POLICY_HALT,
    CHECKLIST_ITEM_BLOCKED_REASON_MAX_LENGTH,
    CHECKLIST_ITEM_LABEL_MAX_LENGTH,
    CHECKLIST_ITEM_NOTES_MAX_LENGTH,
)


class ChecklistItemIn(BaseModel):
    """Request shape for ``POST /api/checklists/{id}/items`` (create).

    Per behavior/checklists.md the user types into the Add-item input;
    parent_item_id may be supplied so the API can support keyboard
    Tab-nest at create time as well as drag-into-parent at create
    time. ``notes`` is optional (the user expands the notes block
    after create more often than at create time).
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=CHECKLIST_ITEM_LABEL_MAX_LENGTH)
    parent_item_id: int | None = None
    notes: str | None = Field(default=None, max_length=CHECKLIST_ITEM_NOTES_MAX_LENGTH)


class ChecklistItemUpdate(BaseModel):
    """Request shape for ``PATCH /api/checklist-items/{id}`` (edit).

    Both fields are optional — the API distinguishes "unchanged" via
    ``None``. Pydantic's ``extra="forbid"`` rejects unknown keys.
    """

    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(
        default=None, min_length=1, max_length=CHECKLIST_ITEM_LABEL_MAX_LENGTH
    )
    notes: str | None = Field(default=None, max_length=CHECKLIST_ITEM_NOTES_MAX_LENGTH)


class ChecklistItemOut(BaseModel):
    """Response shape for a single checklist item."""

    model_config = ConfigDict(extra="forbid")

    id: int
    checklist_id: str
    parent_item_id: int | None
    label: str
    notes: str | None
    sort_order: int
    checked_at: str | None
    chat_session_id: str | None
    blocked_at: str | None
    blocked_reason_category: str | None
    blocked_reason_text: str | None
    created_at: str
    updated_at: str


class MoveItemIn(BaseModel):
    """Request shape for ``POST /api/checklist-items/{id}/move``."""

    model_config = ConfigDict(extra="forbid")

    parent_item_id: int | None = None
    sort_order: int | None = None


class LinkChatIn(BaseModel):
    """Request shape for ``POST /api/checklist-items/{id}/link``."""

    model_config = ConfigDict(extra="forbid")

    chat_session_id: str = Field(min_length=1)
    spawned_by: str = Field(default="user", min_length=1)


class OutcomeIn(BaseModel):
    """Request shape for ``POST /api/checklist-items/{id}/block`` etc.

    ``category`` is one of ``blocked`` / ``failed`` / ``skipped``.
    ``reason`` is optional free-text.
    """

    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=CHECKLIST_ITEM_BLOCKED_REASON_MAX_LENGTH)


class PairedChatLegOut(BaseModel):
    """Response shape for one leg row."""

    model_config = ConfigDict(extra="forbid")

    id: int
    checklist_item_id: int
    chat_session_id: str
    leg_number: int
    spawned_by: str
    created_at: str
    closed_at: str | None


class StartRunIn(BaseModel):
    """Request shape for ``POST /api/checklists/{id}/run/start``.

    Per behavior/checklists.md §"Run-control surface" the user picks
    failure_policy ∈ {halt, skip} (default halt) and the
    visit_existing toggle before pressing Start.
    """

    model_config = ConfigDict(extra="forbid")

    failure_policy: str = Field(default=AUTO_DRIVER_FAILURE_POLICY_HALT, min_length=1)
    visit_existing: bool = False


class AutoDriverRunOut(BaseModel):
    """Response shape for the auto-driver run row."""

    model_config = ConfigDict(extra="forbid")

    id: int
    checklist_id: str
    state: str
    failure_policy: str
    visit_existing: bool
    items_completed: int
    items_failed: int
    items_blocked: int
    items_skipped: int
    items_attempted: int
    legs_spawned: int
    current_item_id: int | None
    outcome: str | None
    outcome_reason: str | None
    started_at: str
    updated_at: str
    finished_at: str | None


class ChecklistOverviewOut(BaseModel):
    """Response shape for ``GET /api/checklists/{id}``.

    Bundles the items list + the active-run row (if any) into one
    payload so the client renders the pane without two roundtrips.
    """

    model_config = ConfigDict(extra="forbid")

    checklist_id: str
    items: list[ChecklistItemOut]
    active_run: AutoDriverRunOut | None


__all__ = [
    "AutoDriverRunOut",
    "ChecklistItemIn",
    "ChecklistItemOut",
    "ChecklistItemUpdate",
    "ChecklistOverviewOut",
    "LinkChatIn",
    "MoveItemIn",
    "OutcomeIn",
    "PairedChatLegOut",
    "StartRunIn",
]
