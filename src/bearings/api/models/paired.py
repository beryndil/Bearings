"""Paired-chat spawn DTO (v0.5.0, Slice 4 of nimble-checking-heron)."""

from __future__ import annotations

from pydantic import BaseModel


class PairedChatCreate(BaseModel):
    """Body for the per-item "Work on this" spawn endpoint
    (`POST /sessions/{id}/checklist/items/{item_id}/chat`). Same
    shape as `SessionCreate` minus `kind` (paired chats are always
    `kind='chat'`) and minus the implicit pairing (server fills in
    `checklist_item_id` from the URL). `tag_ids` is required and
    defaults are inherited from the parent checklist session when
    the client doesn't override them.

    Added in v0.5.0 (Slice 4 of nimble-checking-heron)."""

    working_dir: str | None = None
    model: str | None = None
    title: str | None = None
    description: str | None = None
    max_budget_usd: float | None = None
    tag_ids: list[int] = []
