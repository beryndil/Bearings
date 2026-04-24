"""Message-level DTOs: wire shape, flag patch body, and aggregate token
totals served by `/sessions/{id}/tokens`."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, field_validator


class Attachment(BaseModel):
    """One file attachment on a user message. `n` is the 1-indexed
    token number the user sees in the composer (`[File 1]`), `path` is
    the absolute on-disk path under the configured upload dir that
    gets substituted in when the turn is sent to the SDK, and
    `filename` + `size_bytes` are the display metadata the transcript
    chip renders. See migration 0027."""

    n: int
    path: str
    filename: str
    size_bytes: int


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    thinking: str | None = None
    created_at: str
    # Per-turn token counts from `ResultMessage.usage`, populated on
    # assistant messages that completed normally. Null on user rows and
    # on assistant rows from before migration 0011 (backfilling them
    # would require replaying the SDK against the CLI, which we won't
    # do). The UI sums non-null values for session totals and falls
    # back to "—" when every row is null.
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    # Message flag pair (migration 0023). `pinned` floats the row in the
    # conversation header without affecting the prompt. `hidden_from_context`
    # drops the row from the history window assembled for the next turn;
    # the row still renders (greyed) in the conversation so the user can
    # toggle it back. Both default False via the column default so pre-0023
    # rows serialize cleanly.
    pinned: bool = False
    hidden_from_context: bool = False
    # Terminal-style file attachments (migration 0027). Populated on
    # user rows whose prompt carried `[File N]` tokens; None on every
    # other row. Order by `n` ascending matches the composer's
    # insertion order and the chip render order in the bubble.
    attachments: list[Attachment] | None = None

    @field_validator("attachments", mode="before")
    @classmethod
    def _decode_attachments_json(cls, value: Any) -> Any:
        """The DB column stores a JSON-encoded string (see migration
        0027 + `db/_messages.py`); Pydantic's default coercion can't
        turn a string into `list[Attachment]`, so we pre-parse here so
        every SELECT path (`routes_sessions`, `routes_messages`,
        search) can construct `MessageOut(**row)` without massaging
        the dict first. Non-string values (already a list, or None)
        pass through untouched for constructors that pass typed data
        (tests, future in-memory factories)."""
        if value is None or isinstance(value, list):
            return value
        if isinstance(value, str):
            if not value:
                return None
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # Corrupt row — drop to None rather than 500 on list.
                return None
        return value


class MessagePatchBody(BaseModel):
    """Partial update for a message's flag columns. Any unset field is
    left unchanged. Added in Phase 8 of docs/context-menu-plan.md — the
    only message mutation we expose is flag toggling; content/thinking
    stay immutable because editing a prior turn would desync the SDK's
    view of the conversation from the DB."""

    pinned: bool | None = None
    hidden_from_context: bool | None = None


class TokenTotalsOut(BaseModel):
    """Aggregate per-session token counts served by
    `/sessions/{id}/tokens`. Every field is a non-negative int —
    NULL rows in the underlying table contribute 0 via COALESCE, so
    a session with zero usable rows returns all-zeros rather than
    null."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
