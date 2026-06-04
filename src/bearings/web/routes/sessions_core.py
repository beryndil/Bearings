"""Core session CRUD routes — list, create, get, delete, close, reopen.

These are the fundamental session lifecycle endpoints per arch §1.1.5.
Model/permission patches live in ``sessions_model``, prompt/regenerate in
``sessions_prompts``, aggregated views in ``sessions_assembly``, and
export/import/work-evidence in ``sessions_io``.
"""

from __future__ import annotations

import logging
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from bearings.config.constants import (
    CLOSEABLE_SESSION_KINDS,
    KNOWN_SESSION_KINDS,
    SESSIONS_DEFAULT_PAGE_SIZE,
    SESSIONS_MAX_PAGE_SIZE,
)
from bearings.db import checklists as checklists_db
from bearings.db import sessions as sessions_db
from bearings.db import tags as tags_db
from bearings.web.models.sessions import (
    SessionCreate,
    SessionOut,
    SessionsPage,
)
from bearings.web.routes._sessions_helpers import (
    _batch_fetch_tags_out,
    _db,
    _fetch_tags_out,
    _resolve_working_dir_from_tags,
    _sessions_broadcaster,
    _to_out,
    _validate_session_tag_ids,
)
from bearings.web.routes.tags import _validate_tag_cardinality

router = APIRouter()
_log = logging.getLogger(__name__)


async def _build_paired_info_map(
    db: aiosqlite.Connection,
    rows: list[sessions_db.Session],
) -> dict[str, str | None]:
    """Build a map of chat session_id → paired parent title for sidebar display."""
    info_map: dict[str, str | None] = {}
    for row in rows:
        if row.kind == "chat" and row.checklist_item_id is not None:
            info = await sessions_db.get_paired_chat_info(db, row.id)
            info_map[row.id] = info[0] if info else None
    return info_map


# ---- list / fetch -----------------------------------------------------------


@router.get("/api/sessions", response_model=SessionsPage, operation_id="list-sessions")
async def list_sessions(
    request: Request,
    kind: str | None = None,
    include_closed: bool = True,
    tag_ids: Annotated[list[int] | None, Query(deprecated=True)] = None,
    tag_ids_project: Annotated[list[int] | None, Query()] = None,
    tag_ids_severity: Annotated[list[int] | None, Query()] = None,
    tag_ids_other: Annotated[list[int] | None, Query()] = None,
    severity_none: bool = False,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=SESSIONS_MAX_PAGE_SIZE,
            description=(
                f"Maximum sessions to return per page (1-{SESSIONS_MAX_PAGE_SIZE}). "
                f"Default {SESSIONS_DEFAULT_PAGE_SIZE}."
            ),
        ),
    ] = SESSIONS_DEFAULT_PAGE_SIZE,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Zero-based row offset for pagination. Default 0 (first page).",
        ),
    ] = 0,
) -> SessionsPage:
    """List sessions filtered by ``kind`` + ``include_closed`` + tag filters (paginated).

    ``limit`` / ``offset`` / ``next_offset`` implement the page contract
    (PERF-BUG-001 + PERF-BUG-005). ``tag_ids`` is the legacy flat OR filter;
    ``tag_ids_project`` / ``tag_ids_severity`` / ``tag_ids_other`` are the
    three-section faceted filter.  ``severity_none=true`` adds the "No
    severity" synthetic filter (gap-cycle-18-003).
    """
    db = _db(request)
    if kind is not None and kind not in KNOWN_SESSION_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"kind {kind!r} not in {sorted(KNOWN_SESSION_KINDS)}",
        )
    tag_filter = tuple(tag_ids) if tag_ids else None
    project_filter = tuple(tag_ids_project) if tag_ids_project else None
    severity_filter = tuple(tag_ids_severity) if tag_ids_severity else None
    other_filter = tuple(tag_ids_other) if tag_ids_other else None
    rows, total = await sessions_db.list_paged(
        db,
        kind=kind,
        include_closed=include_closed,
        tag_ids=tag_filter,
        tag_ids_project=project_filter,
        tag_ids_severity=severity_filter,
        tag_ids_other=other_filter,
        severity_none=severity_none,
        limit=limit,
        offset=offset,
    )
    paired_info_map = await _build_paired_info_map(db, rows)
    session_ids = [row.id for row in rows]
    tags_map = await _batch_fetch_tags_out(db, session_ids)
    page_sessions = [
        _to_out(
            row,
            paired_parent_title=paired_info_map.get(row.id),
            tags=tags_map.get(row.id),
        )
        for row in rows
    ]
    delivered = offset + len(rows)
    next_offset: int | None = delivered if delivered < total else None
    return SessionsPage(sessions=page_sessions, total=total, next_offset=next_offset)


@router.post(
    "/api/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="create-session",
)
async def create_session(
    payload: SessionCreate,
    request: Request,
    response: Response,
) -> SessionOut:
    """Create a session row + attach tags atomically.

    ``kind`` must be in :data:`KNOWN_SESSION_KINDS`.  Every id in
    ``tag_ids`` must reference an existing tag row (checked before INSERT).
    ``working_dir`` is resolved from the first tag with a non-null
    ``working_dir`` when not supplied explicitly.  Returns 201 +
    ``Location: /api/sessions/<id>``.
    """
    db = _db(request)
    if payload.kind not in KNOWN_SESSION_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"kind {payload.kind!r} not in {sorted(KNOWN_SESSION_KINDS)}",
        )
    tag_ids = tuple(payload.tag_ids)
    if tag_ids:
        await _validate_session_tag_ids(db, tag_ids)
        await _validate_tag_cardinality(db, tag_ids)
    resolved_working_dir = payload.working_dir
    if resolved_working_dir is None and tag_ids:
        resolved_working_dir = await _resolve_working_dir_from_tags(db, tag_ids)
    if resolved_working_dir is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="working_dir is required — supply it explicitly or attach a tag with "
            "a working_dir set",
        )
    try:
        row = await sessions_db.create(
            db,
            kind=payload.kind,
            title=payload.title,
            working_dir=resolved_working_dir,
            model=payload.model,
            description=payload.description,
            session_instructions=payload.session_instructions,
            permission_mode=payload.permission_mode,
            max_budget_usd=payload.max_budget_usd,
            routing_advisor_model=payload.routing_advisor_model,
            routing_advisor_max_uses=payload.routing_advisor_max_uses,
            routing_effort_level=payload.routing_effort_level,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if tag_ids:
        await tags_db.set_for_session(db, session_id=row.id, tag_ids=tag_ids)
    embedded_tags = await _fetch_tags_out(db, row.id)
    out = _to_out(row, tags=embedded_tags)
    broadcaster = _sessions_broadcaster(request)
    if broadcaster is not None:
        broadcaster.publish_upsert(out)
    response.headers["Location"] = f"/api/sessions/{row.id}"
    return out


@router.get("/api/sessions/{session_id}", response_model=SessionOut, operation_id="get-session")
async def get_session(session_id: str, request: Request) -> SessionOut:
    """Fetch one session by id; 404 if absent."""
    db = _db(request)
    row = await sessions_db.get(db, session_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    paired_parent_title: str | None = None
    if row.kind == "chat" and row.checklist_item_id is not None:
        info = await sessions_db.get_paired_chat_info(db, session_id)
        paired_parent_title = info[0] if info else None
    tags = await _fetch_tags_out(db, session_id)
    return _to_out(row, paired_parent_title=paired_parent_title, tags=tags)


@router.delete(
    "/api/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete-session",
)
async def delete_session(session_id: str, request: Request) -> None:
    """Cascade-delete a session row + messages + checkpoints.

    Explicitly NULLs ``chat_session_id`` on any checklist items that
    referenced it (belt-and-suspenders on top of ON DELETE SET NULL).
    """
    db = _db(request)
    removed = await sessions_db.delete(db, session_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    await checklists_db.clear_orphaned_chat_session_id(db, session_id)
    broadcaster = _sessions_broadcaster(request)
    if broadcaster is not None:
        broadcaster.publish_delete(session_id)


@router.post(
    "/api/sessions/{session_id}/close",
    response_model=SessionOut,
    operation_id="close-session",
)
async def close_session(session_id: str, request: Request) -> SessionOut:
    """Stamp ``closed_at`` (only for kinds in :data:`CLOSEABLE_SESSION_KINDS`).

    Returns 422 for checklist sessions (not subject to the close/reopen
    lifecycle per ``docs/behavior/checklists.md``).
    """
    db = _db(request)
    existing_kind = await sessions_db.get_kind(db, session_id)
    if existing_kind is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    if existing_kind not in CLOSEABLE_SESSION_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"sessions of kind {existing_kind!r} cannot be closed; "
                f"close is only supported for: {sorted(CLOSEABLE_SESSION_KINDS)}"
            ),
        )
    row = await sessions_db.close(db, session_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    tags = await _fetch_tags_out(db, session_id)
    out = _to_out(row, tags=tags)
    broadcaster = _sessions_broadcaster(request)
    if broadcaster is not None:
        broadcaster.publish_upsert(out)
    return out


@router.post(
    "/api/sessions/{session_id}/reopen",
    response_model=SessionOut,
    operation_id="reopen-session",
)
async def reopen_session(session_id: str, request: Request) -> SessionOut:
    """Clear ``closed_at`` per behavior doc §"Reopen semantics"."""
    db = _db(request)
    row = await sessions_db.reopen(db, session_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    tags = await _fetch_tags_out(db, session_id)
    out = _to_out(row, tags=tags)
    broadcaster = _sessions_broadcaster(request)
    if broadcaster is not None:
        broadcaster.publish_upsert(out)
    return out
