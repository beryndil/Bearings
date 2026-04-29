# mypy: disable-error-code=explicit-any
"""Pydantic wire shapes for ``routes/paired_chats.py``.

Per ``docs/architecture-v1.md`` §1.1.5 the wire DTOs live alongside
the route module. The shapes mirror the spawn-and-link service
(:func:`bearings.agent.paired_chats.spawn_paired_chat`) and the
detach-from-chat-side endpoint.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from bearings.config.constants import (
    PAIRED_CHAT_SPAWNED_BY_USER,
    SESSION_DESCRIPTION_MAX_LENGTH,
    SESSION_TITLE_MAX_LENGTH,
)


class SpawnPairedChatIn(BaseModel):
    """Request shape for ``POST /api/checklist-items/{id}/spawn-chat``.

    Per ``docs/behavior/paired-chats.md`` §"Spawning a new pair" the
    ``💬 Work on this`` click takes no arguments — the chat title
    defaults to the item's label. The optional ``title`` and ``plug``
    fields cover the auto-driver leg-spawn path and a future "spawn
    with custom title" UI affordance.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=SESSION_TITLE_MAX_LENGTH)
    plug: str | None = Field(default=None, max_length=SESSION_DESCRIPTION_MAX_LENGTH)
    spawned_by: str = Field(default=PAIRED_CHAT_SPAWNED_BY_USER, min_length=1)


class SpawnPairedChatOut(BaseModel):
    """Response shape for the spawn endpoint.

    The route returns ``201 Created`` on first spawn and ``200 OK``
    when the idempotent path returns an existing pair (per
    ``docs/behavior/paired-chats.md`` §"Spawning a new pair" — the
    second click "selects the same session the first one created"; the
    distinct status code lets a client distinguish without comparing
    response bodies).
    """

    model_config = ConfigDict(extra="forbid")

    chat_session_id: str
    item_id: int
    title: str
    working_dir: str
    model: str
    created: bool


__all__ = ["SpawnPairedChatIn", "SpawnPairedChatOut"]
