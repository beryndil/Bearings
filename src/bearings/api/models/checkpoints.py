"""Checkpoint DTOs (Phase 7 of docs/context-menu-plan.md). Checkpoints
anchor a named reference at a specific turn and can later be forked
into a new session."""

from __future__ import annotations

from pydantic import BaseModel


class CheckpointCreate(BaseModel):
    """Body for `POST /sessions/{id}/checkpoints`. `message_id` anchors
    the checkpoint at a specific turn; `label` is optional because an
    auto-checkpoint ("before risky prompt") doesn't need a name. Added
    in Phase 7 of docs/context-menu-plan.md."""

    message_id: str
    label: str | None = None


class CheckpointOut(BaseModel):
    """Wire shape for a checkpoint row. `message_id` is nullable to
    reflect the `ON DELETE SET NULL` FK — a checkpoint whose anchor
    message got dropped in a reorg audit stays alive as a session-level
    label with `message_id = null`. Added in Phase 7."""

    id: str
    session_id: str
    message_id: str | None
    label: str | None
    created_at: str


class CheckpointForkRequest(BaseModel):
    """Body for `POST /sessions/{id}/checkpoints/{cid}/fork`. `title`
    renames the resulting session; when omitted the fork inherits the
    source session's title with a " (fork)" suffix. Added in Phase 7."""

    title: str | None = None
