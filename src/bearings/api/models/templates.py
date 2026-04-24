"""Template DTOs (Phase 9b of docs/context-menu-plan.md). Templates
save reusable session configurations and can be instantiated with
per-call overrides."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TemplateCreate(BaseModel):
    """Body for `POST /templates`. `name` is required; everything else
    is nullable so a blank scratchpad template is legal. `tag_ids`
    carries attach-time tag associations — unknown ids are silently
    dropped at instantiation time (the source tag may have been
    deleted since the template was saved). Added in Phase 9b of
    docs/context-menu-plan.md."""

    name: str = Field(min_length=1)
    body: str | None = None
    working_dir: str | None = None
    model: str | None = None
    session_instructions: str | None = None
    tag_ids: list[int] = Field(default_factory=list)


class TemplateOut(BaseModel):
    """Wire shape for a template row. Mirrors the store dict with
    `tag_ids` already decoded (store layer owns the JSON encoding).
    Added in Phase 9b."""

    id: str
    name: str
    body: str | None = None
    working_dir: str | None = None
    model: str | None = None
    session_instructions: str | None = None
    tag_ids: list[int] = Field(default_factory=list)
    created_at: str


class TemplateInstantiateRequest(BaseModel):
    """Body for `POST /sessions/from_template/{id}`. Every field
    overrides the saved template — a user who wants to tweak the
    working_dir once without editing the template supplies just that
    field. Omitted fields fall through to the template's saved value;
    the template's null fields fall through to app defaults. The
    `body` field, when present and non-empty, is turned into the
    first user message on the new session (same as the regular
    `NewSessionForm` initial-prompt path). Added in Phase 9b."""

    title: str | None = None
    working_dir: str | None = None
    model: str | None = None
    session_instructions: str | None = None
    body: str | None = None
