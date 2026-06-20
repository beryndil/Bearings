# mypy: disable-error-code=explicit-any
"""Reorg REST endpoints (gap-cycle-03-008/009, gap-cycle-13-002).

Per ``docs/architecture-v1.md`` §1.1.5 this module owns:

* ``POST /api/sessions/{src_id}/reorg/merge?target={dst_id}`` — merge
  ``src_id`` into ``dst_id`` atomically.  Writes a ``kind='merge'`` audit
  row, then deletes the source session.
* ``POST /api/sessions/{src_id}/reorg/split?target={dst_id}&from_seq={n}``
  — split ``src_id`` at message ``n``.  Re-parents all messages with
  ``rowid >= n`` to ``dst_id`` atomically and writes a ``kind='split'``
  audit row.  Returns :class:`ReorgSplitOut` (audit + moved message ids).
* ``POST /api/sessions/{src_id}/reorg/move?target={dst_id}&message_id={id}``
  — move a single message from ``src_id`` to ``dst_id`` atomically and
  write a ``kind='move'`` audit row.  Returns :class:`ReorgAuditOut`.
* ``GET /api/sessions/{id}/reorg/audits`` — list all audit rows for the
  session ``id`` (all kinds, oldest-first).
* ``DELETE /api/sessions/{id}/reorg/audits/{audit_id}`` — atomically
  reverse any reorg operation and remove the audit row.  Returns 200 with
  :class:`UndoReorgOut` on success, 404 when absent, 409 when stale.

Common error responses:

* 409 when ``src_id == dst_id``.
* 404 when either session (or the specified message) does not exist.
"""

from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from bearings.db import messages as messages_db
from bearings.db import reorg as reorg_db
from bearings.web.models.reorg import (
    ReorgAuditListOut,
    ReorgAuditOut,
    ReorgSplitOut,
    UndoReorgOut,
)

_log = logging.getLogger(__name__)

_ANALYZE_GAP_MS: int = 30 * 60 * 1000  # 30-minute gap → proposed boundary
_ANALYZE_CHUNK_SIZE: int = 10  # every N turns → proposed boundary

# Backward-compat: routes that were already imported elsewhere still work.
UndoMergeOut = UndoReorgOut

router = APIRouter()


def _db(request: Request) -> aiosqlite.Connection:
    """Pull the long-lived DB connection off ``app.state`` (503 if absent)."""
    conn: aiosqlite.Connection | None = getattr(request.app.state, "db_connection", None)
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database not available",
        )
    return conn


def _to_out(audit: reorg_db.ReorgAudit) -> ReorgAuditOut:
    return ReorgAuditOut(
        id=audit.id,
        dst_session_id=audit.dst_session_id,
        src_session_id=audit.src_session_id,
        merged_at=audit.merged_at,
        src_title=audit.src_title,
        boundary_msg_id=audit.boundary_msg_id,
        kind=audit.kind,
    )


@router.post(
    "/api/sessions/{src_id}/reorg/merge",
    response_model=ReorgAuditOut,
    status_code=status.HTTP_200_OK,
    operation_id="reorg-merge-sessions",
)
async def merge_session(
    src_id: str,
    request: Request,
    target: str = Query(..., description="Destination session id to merge into"),
) -> ReorgAuditOut:
    """Merge ``src_id`` into ``target`` in one atomic transaction.

    Re-parents every message from the source session to the destination,
    writes a ``reorg_audit`` row (carrying the id of the first
    re-parented message as ``boundary_msg_id``), then deletes the source
    session. Cascade deletes clean up the source's checkpoints, tags,
    sdk_session_entries, and other FK-linked rows.

    Returns 200 with the audit row on success.
    Returns 409 when ``src_id == target`` (self-merge).
    Returns 404 when either session does not exist.
    """
    if src_id == target:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="src and target session ids must differ (self-merge is not permitted)",
        )
    db = _db(request)
    result = await reorg_db.merge_sessions(db, src_id, target)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"one or both sessions not found: src={src_id!r} target={target!r}",
        )
    return _to_out(result)


@router.post(
    "/api/sessions/{src_id}/reorg/split",
    response_model=ReorgSplitOut,
    status_code=status.HTTP_200_OK,
    operation_id="reorg-split-session",
)
async def fork_session(
    src_id: str,
    request: Request,
    target: str = Query(..., description="Destination session id"),
    from_seq: int = Query(..., description="Rowid of the first message to re-parent"),
) -> ReorgSplitOut:
    """Split ``src_id`` at ``from_seq`` into ``target`` atomically.

    Re-parents all messages in ``src_id`` with ``rowid >= from_seq`` to
    ``target`` in a single transaction and writes a ``kind='split'`` audit
    row.  The divider will live in ``src_id``; ``target`` is the
    destination that received the content.

    Returns 200 with the audit row and the list of moved message ids.
    Returns 409 when ``src_id == target`` (self-split is not permitted).
    Returns 404 when either session does not exist.
    """
    if src_id == target:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="src and target session ids must differ (self-split is not permitted)",
        )
    db = _db(request)
    result = await reorg_db.split_session(db, src_id, target, from_seq)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"one or both sessions not found: src={src_id!r} target={target!r}",
        )
    return ReorgSplitOut(
        audit=_to_out(result.audit),
        moved_message_ids=result.moved_message_ids,
    )


@router.post(
    "/api/sessions/{src_id}/reorg/move",
    response_model=ReorgAuditOut,
    status_code=status.HTTP_200_OK,
    operation_id="reorg-move-message",
)
async def move_message(
    src_id: str,
    request: Request,
    target: str = Query(..., description="Destination session id"),
    message_id: str = Query(..., description="Id of the message to move"),
) -> ReorgAuditOut:
    """Move a single message from ``src_id`` to ``target`` atomically.

    Re-parents the message in a single transaction and writes a
    ``kind='move'`` audit row.  The divider lives in ``src_id``.

    Returns 200 with the audit row.
    Returns 409 when ``src_id == target``.
    Returns 404 when either session or the message is not found in ``src_id``.
    """
    if src_id == target:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="src and target session ids must differ",
        )
    db = _db(request)
    audit = await reorg_db.move_message_reorg(db, src_id, target, message_id)
    if audit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"session or message not found: src={src_id!r} target={target!r} "
                f"message_id={message_id!r}"
            ),
        )
    return _to_out(audit)


@router.get(
    "/api/sessions/{dst_id}/reorg/audits",
    response_model=ReorgAuditListOut,
    status_code=status.HTTP_200_OK,
    operation_id="list-reorg-audits",
)
async def list_reorg_audits(
    dst_id: str,
    request: Request,
) -> ReorgAuditListOut:
    """Return all reorg audit rows for ``dst_id`` (all kinds), oldest-first.

    ``dst_id`` is the session that hosts the divider for each kind.
    Used by the frontend on conversation load to hydrate persistent
    divider rows.  Returns an empty list when no reorg operations have
    been recorded for this session.
    """
    db = _db(request)
    rows = await reorg_db.list_audit_for_session(db, dst_id)
    return ReorgAuditListOut(items=[_to_out(r) for r in rows])


@router.delete(
    "/api/sessions/{dst_id}/reorg/audits/{audit_id}",
    response_model=UndoReorgOut,
    status_code=status.HTTP_200_OK,
    operation_id="undo-reorg",
)
async def delete_reorg_audit(
    dst_id: str,
    audit_id: str,
    request: Request,
) -> UndoReorgOut:
    """Atomically reverse any reorg operation and delete the audit row.

    Dispatches based on the audit row's ``kind``:

    * ``merge``: re-creates the source session, moves merged messages back.
    * ``split``: moves split messages from the target back to ``dst_id``.
    * ``move``: moves the single message from the target back to ``dst_id``.

    Returns 200 with ``new_session_id`` on success.
    Returns 404 when ``audit_id`` is absent or does not belong to ``dst_id``.
    Returns 409 when the relevant session has been mutated since the operation.
    """
    db = _db(request)
    try:
        new_session_id = await reorg_db.undo_merge_audit(db, audit_id, dst_id)
    except reorg_db.StaleAuditError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if new_session_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"reorg audit not found: {audit_id!r} for session {dst_id!r}",
        )
    return UndoReorgOut(new_session_id=new_session_id)


# ---------------------------------------------------------------------------
# Analyze — heuristic split/extract suggestion (N-11 / R-2)
# ---------------------------------------------------------------------------


def _ts_ms(created_at: str | None) -> float:
    """Parse an ISO-8601 *created_at* string to a millisecond POSIX timestamp.

    Returns ``0.0`` when *created_at* is absent or cannot be parsed.  Callers
    treat ``0.0`` as "no timestamp available" and skip time-gap checks.
    """
    if not created_at:
        return 0.0
    from datetime import datetime

    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp() * 1000
    except (ValueError, AttributeError):
        return 0.0


class ReorgProposal(BaseModel):
    """One proposed split boundary from ``POST /api/sessions/{id}/reorg/analyze``."""

    message_id: str
    reason: str


class ReorgAnalyzeOut(BaseModel):
    """Response shape for ``POST /api/sessions/{id}/reorg/analyze``."""

    proposals: list[ReorgProposal]
    source: str  # "heuristic" | "llm"


@router.post(
    "/api/sessions/{session_id}/reorg/analyze",
    response_model=ReorgAnalyzeOut,
    status_code=status.HTTP_200_OK,
    operation_id="reorg-analyze-session",
    summary="Heuristic + optional LLM-backed split/extract suggestion",
)
async def run_reorg_analysis(
    session_id: str,
    request: Request,
    chunk_size: int = Query(
        default=_ANALYZE_CHUNK_SIZE,
        ge=2,
        le=100,
        description="Propose a boundary every N turns (chunk heuristic).",
    ),
) -> ReorgAnalyzeOut:
    """Analyse ``session_id`` and propose split boundaries.

    Heuristic rules (applied in order per message position):

    1. A time gap of ≥ 30 min between consecutive turns suggests a new
       topic → propose a boundary at the later message.
    2. Every ``chunk_size`` turns (default 10) a natural chunk boundary
       is proposed.

    Returns 404 when the session does not exist.  Returns an empty
    ``proposals`` list when the session has fewer than 2 messages.

    LLM-backed suggestions are not implemented in this release; the
    ``source`` field is always ``"heuristic"``.  The advisor pattern
    is wired into the framework for a future iteration.
    """
    db = _db(request)
    msgs = await messages_db.list_for_session(db, session_id)
    if not msgs:
        # Validate session existence — return 404 for unknown ids.
        from bearings.db import sessions as sessions_db  # local to avoid circular

        row = await sessions_db.get(db, session_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no session matches {session_id!r}",
            )

    proposals: list[ReorgProposal] = []
    for idx, msg in enumerate(msgs):
        if idx == 0:
            continue
        prev = msgs[idx - 1]

        prev_ts = _ts_ms(prev.created_at)
        cur_ts = _ts_ms(msg.created_at)

        if prev_ts > 0 and cur_ts > 0 and (cur_ts - prev_ts) >= _ANALYZE_GAP_MS:
            gap_min = int((cur_ts - prev_ts) / 60_000)
            proposals.append(
                ReorgProposal(
                    message_id=msg.id,
                    reason=f"~{gap_min} min gap before this message",
                )
            )
            continue

        if idx % chunk_size == 0:
            proposals.append(
                ReorgProposal(
                    message_id=msg.id,
                    reason=f"Natural chunk boundary at message {idx + 1}",
                )
            )

    return ReorgAnalyzeOut(proposals=proposals, source="heuristic")


__all__ = ["router"]
