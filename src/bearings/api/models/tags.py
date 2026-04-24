"""Tag DTOs and the `TagGroup` Literal guard.

Tag grouping dimension (migration 0021). 'general' = the user-
configurable tag set; 'severity' = the Blocker/Critical/Medium/Low/
QoL urgency ladder every session carries. Declared as a Literal so a
typo in the request body surfaces as a 422 at the boundary instead
of landing in the DB and tripping the CHECK constraint.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

TagGroup = Literal["general", "severity"]


class TagCreate(BaseModel):
    name: str
    color: str | None = None
    pinned: bool = False
    sort_order: int = 0
    default_working_dir: str | None = None
    default_model: str | None = None
    # Defaults to 'general' so existing callers (Settings → New tag,
    # tests, tooling) keep working without change. Set 'severity' to
    # land the tag in the second filter section.
    tag_group: TagGroup = "general"


class TagUpdate(BaseModel):
    """Partial update for an existing tag. Any unset field is left
    unchanged; explicit `None` for nullable fields clears them."""

    name: str | None = None
    color: str | None = None
    pinned: bool | None = None
    sort_order: int | None = None
    default_working_dir: str | None = None
    default_model: str | None = None
    # Moving a tag between groups is allowed — a user who renamed their
    # existing "Blocker" tag before migration 0021 landed can promote
    # it into the severity group with a single PATCH. Unset = unchanged.
    tag_group: TagGroup | None = None


class TagOut(BaseModel):
    id: int
    name: str
    color: str | None = None
    pinned: bool
    sort_order: int
    created_at: str
    session_count: int = 0
    # Open-only partition of session_count (sessions whose closed_at is
    # NULL). Rendered in green beside the total on the sidebar.
    open_session_count: int = 0
    default_working_dir: str | None = None
    default_model: str | None = None
    # Filter-panel section the tag renders in (migration 0021). The
    # frontend groups tags client-side off this field and paints the
    # severity section below an HR divider with no Any/All toggle.
    tag_group: TagGroup = "general"


class TagMemoryPut(BaseModel):
    content: str


class TagMemoryOut(BaseModel):
    tag_id: int
    content: str
    updated_at: str
