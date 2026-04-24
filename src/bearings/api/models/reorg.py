"""Reorg-operation DTOs: move / split / merge request & result shapes
plus the persistent audit row."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .sessions import NewSessionSpec, SessionOut


class ReorgWarning(BaseModel):
    """Advisory issue surfaced by a reorg op — never fatal.

    Slice 2 always returns an empty `warnings` array; Slice 7 (Polish)
    populates this with tool-call-group split detection. The model is
    defined now so the API shape is stable and the future addition is
    non-breaking.
    """

    code: str
    message: str
    details: dict[str, str] = {}


class ReorgMoveRequest(BaseModel):
    """Body for `POST /sessions/{id}/reorg/move`. `message_ids` must
    be non-empty; the route rejects an empty list with 400 even though
    the underlying primitive tolerates it as a no-op."""

    target_session_id: str
    message_ids: list[str]


class ReorgMoveResult(BaseModel):
    """Response shape shared by `move` and (nested in) `split`.

    `moved` and `tool_calls_followed` come directly from
    `store.MoveResult`; `warnings` is the forward-compatible slot for
    Slice 7's group-split detection — currently always `[]`. `audit_id`
    is the row the route wrote to `reorg_audits`; `None` when the op
    was a no-op (zero moves) so no divider was recorded. The frontend
    threads this into its undo handler so `DELETE /reorg/audits/{id}`
    has a direct target — no lookup race against a concurrent second
    op landing in the same millisecond.
    """

    moved: int
    tool_calls_followed: int
    warnings: list[ReorgWarning] = []
    audit_id: int | None = None


class ReorgSplitRequest(BaseModel):
    """Body for `POST /sessions/{id}/reorg/split`. `after_message_id`
    is the anchor — every message chronologically after it moves into
    the new session."""

    after_message_id: str
    new_session: NewSessionSpec


class ReorgSplitResult(BaseModel):
    """Response shape for split — the newly created session plus the
    inner move counts. 201 status code signals a resource was created."""

    session: SessionOut
    result: ReorgMoveResult


class ReorgMergeRequest(BaseModel):
    """Body for `POST /sessions/{id}/reorg/merge`. Moves every message
    on the source session into `target_session_id` in a single op; set
    `delete_source=true` to drop the now-empty source. Merging a
    session into itself is rejected with a 400."""

    target_session_id: str
    delete_source: bool = False


class ReorgMergeResult(BaseModel):
    """Response shape for merge. Carries the same `moved` /
    `tool_calls_followed` / `warnings` / `audit_id` fields as
    move/split, plus `deleted_source` (always matches the request flag
    on success; flip to false means the DELETE call no-op'd because
    the source was already empty of messages and still-live).

    `audit_id` is `None` when no audit row was written — either a
    no-op merge (zero moves) or a merge that deleted the source (the
    cascade would have dropped the row, so the route skips the write)."""

    moved: int
    tool_calls_followed: int
    warnings: list[ReorgWarning] = []
    audit_id: int | None = None
    deleted_source: bool


class ReorgAuditOut(BaseModel):
    """One persistent divider entry rendered on the source session's
    conversation view. The `target_session_id` FK is `ON DELETE SET
    NULL`, so a stale row with null id + a populated title snapshot
    means "the target was deleted after the move." The UI renders
    "(deleted session)" for that case instead of hiding the row."""

    id: int
    source_session_id: str
    target_session_id: str | None = None
    target_title_snapshot: str | None = None
    message_count: int
    op: Literal["move", "split", "merge"]
    created_at: str
