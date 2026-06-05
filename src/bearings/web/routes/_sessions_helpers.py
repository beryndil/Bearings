"""Shared dependency extractors, tag helpers, and dispatch helper for sessions routes.

This private module is imported by the sessions sub-modules (sessions_core,
sessions_model, sessions_prompts, sessions_assembly, sessions_io) so common
logic lives in one place and is not duplicated across the split.
"""

from __future__ import annotations

import json
import logging
from typing import cast

import aiosqlite
from fastapi import APIRouter, HTTPException, Request, Response, status

from bearings.agent.prompt_dispatch import (
    PromptDispatchOutcome,
    PromptDispatchResult,
    RateLimiter,
)
from bearings.agent.runner import RunnerFactory
from bearings.config.constants import (
    PROMPT_ACK_QUEUED_KEY,
    PROMPT_ACK_SESSION_ID_KEY,
)
from bearings.db import tags as tags_db
from bearings.db.sessions import Session
from bearings.web.models.sessions import SessionOut
from bearings.web.models.tags import TagOut
from bearings.web.routes.ws_sessions import SessionsBroadcaster

_log = logging.getLogger(__name__)

# Re-export APIRouter so sub-modules can do ``from ._sessions_helpers import
# APIRouter`` without an extra fastapi import line.  The shim assembles one
# combined router from sub-routers; each sub-module owns a local router.
__all__ = [
    "APIRouter",
    "_batch_fetch_tags_out",
    "_db",
    "_dispatch_result_to_response",
    "_fetch_tags_out",
    "_rate_limiter",
    "_resolve_working_dir_from_tags",
    "_runner_factory",
    "_sessions_broadcaster",
    "_tag_to_out",
    "_to_out",
    "_validate_session_tag_ids",
]


# ---------------------------------------------------------------------------
# App-state dependency extractors
# ---------------------------------------------------------------------------


def _db(request: Request) -> aiosqlite.Connection:
    """Pull the long-lived DB connection off ``app.state``."""
    db = getattr(request.app.state, "db_connection", None)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_connection not configured on app.state",
        )
    return cast(aiosqlite.Connection, db)


def _runner_factory(request: Request) -> RunnerFactory:
    """Pull the runner factory off ``app.state``."""
    factory = getattr(request.app.state, "runner_factory", None)
    if factory is None:  # pragma: no cover — set by create_app
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="runner_factory not configured on app.state",
        )
    return cast(RunnerFactory, factory)


def _rate_limiter(request: Request) -> RateLimiter:
    """Pull the per-app :class:`RateLimiter` off ``app.state``."""
    limiter = getattr(request.app.state, "prompt_rate_limiter", None)
    if limiter is None:  # pragma: no cover — set by create_app
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="prompt_rate_limiter not configured on app.state",
        )
    if not isinstance(limiter, RateLimiter):  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="prompt_rate_limiter on app.state is not a RateLimiter",
        )
    return limiter


def _sessions_broadcaster(request: Request) -> SessionsBroadcaster | None:
    """Pull the optional sessions broadcaster off ``app.state``.

    Returns ``None`` when no broadcaster is wired (test-only paths).
    """
    return cast(
        SessionsBroadcaster | None,
        getattr(request.app.state, "sessions_broadcaster", None),
    )


# ---------------------------------------------------------------------------
# Row-to-wire converters
# ---------------------------------------------------------------------------


def _to_out(
    session: Session,
    paired_parent_title: str | None = None,
    tags: list[TagOut] | None = None,
) -> SessionOut:
    """Wire shape for a session row."""
    return SessionOut(
        id=session.id,
        kind=session.kind,
        title=session.title,
        description=session.description,
        session_instructions=session.session_instructions,
        working_dir=session.working_dir,
        model=session.model,
        permission_mode=session.permission_mode,
        max_budget_usd=session.max_budget_usd,
        total_cost_usd=session.total_cost_usd,
        message_count=session.message_count,
        last_context_pct=session.last_context_pct,
        last_context_tokens=session.last_context_tokens,
        last_context_max=session.last_context_max,
        pinned=session.pinned,
        error_pending=session.error_pending,
        checklist_item_id=session.checklist_item_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_viewed_at=session.last_viewed_at,
        last_completed_at=session.last_completed_at,
        closed_at=session.closed_at,
        closing_summary=session.closing_summary,
        paired_parent_title=paired_parent_title,
        pivot_message_id=session.pivot_message_id,
        parent_session_id=session.parent_session_id,
        template_id=session.template_id,
        classified=session.classified,
        tags=tags if tags is not None else [],
    )


def _tag_to_out(tag: tags_db.Tag) -> TagOut:
    """Convert a :class:`~bearings.db.tags.Tag` dataclass to :class:`TagOut`."""
    return TagOut(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        default_model=tag.default_model,
        working_dir=tag.working_dir,
        pinned=tag.pinned,
        class_=tag.class_,  # type: ignore[arg-type]
        sort_order=tag.sort_order,
        group=tag.group,
        created_at=tag.created_at,
        updated_at=tag.updated_at,
    )


async def _fetch_tags_out(
    db: aiosqlite.Connection,
    session_id: str,
) -> list[TagOut]:
    """Fetch and convert the tag list for a single session (one SQL round-trip)."""
    raw = await tags_db.list_for_session(db, session_id)
    return [_tag_to_out(t) for t in raw]


async def _batch_fetch_tags_out(
    db: aiosqlite.Connection,
    session_ids: list[str],
) -> dict[str, list[TagOut]]:
    """Single SQL batch-fetch of tags for the session list.

    Returns ``{session_id: [TagOut, …], …}``; sessions with no tags map to ``[]``.
    One round-trip replaces the N+1 fan-out (PERF-NET-01).
    """
    if not session_ids:
        return {}
    placeholders = ",".join("?" * len(session_ids))
    cursor = await db.execute(
        "SELECT st.session_id, t.id, t.name, t.color, t.default_model, "
        "t.working_dir, t.pinned, t.class, t.sort_order, t.created_at, t.updated_at "
        "FROM session_tags st "
        "INNER JOIN tags t ON t.id = st.tag_id "
        f"WHERE st.session_id IN ({placeholders}) "
        "ORDER BY st.session_id ASC, t.name ASC",
        session_ids,
    )
    try:
        rows = await cursor.fetchall()
    finally:
        await cursor.close()
    result: dict[str, list[TagOut]] = {sid: [] for sid in session_ids}
    for row in rows:
        sid = str(row[0])
        tag = tags_db.Tag(
            id=int(str(row[1])),
            name=str(row[2]),
            color=None if row[3] is None else str(row[3]),
            default_model=None if row[4] is None else str(row[4]),
            working_dir=None if row[5] is None else str(row[5]),
            pinned=bool(row[6]),
            class_=str(row[7]),
            sort_order=int(str(row[8])),
            created_at=str(row[9]),
            updated_at=str(row[10]),
        )
        if sid in result:
            result[sid].append(_tag_to_out(tag))
    return result


# ---------------------------------------------------------------------------
# Tag validation helpers
# ---------------------------------------------------------------------------


async def _validate_session_tag_ids(
    db: aiosqlite.Connection,
    tag_ids: tuple[int, ...],
) -> None:
    """Raise 404 HTTPException when any tag_id does not exist."""
    existing_ids = {tag.id for tag in await tags_db.list_all(db)}
    missing = sorted({tid for tid in tag_ids if tid not in existing_ids})
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown tag_ids: {missing}",
        )


async def _resolve_working_dir_from_tags(
    db: aiosqlite.Connection,
    tag_ids: tuple[int, ...],
) -> str | None:
    """Return the first non-null working_dir from the tag_ids, preserving order."""
    tag_list = await tags_db.list_all(db)
    tag_map = {tag.id: tag for tag in tag_list}
    for tid in tag_ids:
        tag = tag_map.get(tid)
        if tag is not None and tag.working_dir is not None:
            return tag.working_dir
    return None


# ---------------------------------------------------------------------------
# Dispatch-result → HTTP response translator
# ---------------------------------------------------------------------------

_DISPATCH_OUTCOME_QUEUED_BODY: dict[str, object] = {
    PROMPT_ACK_QUEUED_KEY: True,
}


def _dispatch_result_to_response(
    result: PromptDispatchResult,
    session_id: str,
) -> Response:
    """Translate a :class:`PromptDispatchResult` to a FastAPI Response.

    Centralises the outcome→HTTP mapping shared by ``prompt_session``,
    ``regenerate_session``, and ``regenerate_from_message``.
    """
    outcome = result.outcome
    if outcome is PromptDispatchOutcome.QUEUED:
        body = dict(_DISPATCH_OUTCOME_QUEUED_BODY)
        body[PROMPT_ACK_SESSION_ID_KEY] = session_id
        return Response(
            content=json.dumps(body),
            status_code=status.HTTP_202_ACCEPTED,
            media_type="application/json",
            headers={"Location": f"/api/sessions/{session_id}"},
        )
    if outcome is PromptDispatchOutcome.NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.detail or f"no session matches {session_id!r}",
        )
    if outcome is PromptDispatchOutcome.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result.detail or "session is closed",
        )
    if outcome is PromptDispatchOutcome.RATE_LIMITED:
        retry_after = result.retry_after_s or 1
        return Response(
            content=json.dumps({"detail": result.detail or "rate limit exceeded"}),
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            media_type="application/json",
            headers={"Retry-After": str(retry_after)},
        )
    code = {
        PromptDispatchOutcome.BAD_KIND: status.HTTP_400_BAD_REQUEST,
        PromptDispatchOutcome.EMPTY_CONTENT: status.HTTP_400_BAD_REQUEST,
        PromptDispatchOutcome.CONTENT_TOO_LARGE: status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    }.get(outcome, status.HTTP_500_INTERNAL_SERVER_ERROR)
    raise HTTPException(
        status_code=code,
        detail=result.detail or f"unhandled dispatch outcome {outcome.value!r}",
    )
