"""Session model/field PATCH routes — model, permission_mode, pinned, full-patch.

Exec-2C will land additional patches in this module (e.g. description).
Keep the session-level update helpers localised here so that diff is clean.
"""

from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, HTTPException, Request, status

from bearings.db import sessions as sessions_db
from bearings.db import tags as tags_db
from bearings.web.models.sessions import (
    SessionModelUpdate,
    SessionOut,
    SessionPermissionModeUpdate,
    SessionPinnedUpdate,
    SessionUpdate,
)
from bearings.web.routes._sessions_helpers import (
    _db,
    _fetch_tags_out,
    _sessions_broadcaster,
    _to_out,
)
from bearings.web.routes.tags import _validate_tag_cardinality
from bearings.web.runner_factory import InProcessRunnerRegistry

router = APIRouter()
_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------


async def _check_tag_ids_exist(
    db: aiosqlite.Connection,
    tag_ids_list: list[int],
) -> None:
    """Raise 422 when any element of *tag_ids_list* is absent from the tags table."""
    existing_ids = {
        int(row[0])
        async for row in await db.execute(
            "SELECT id FROM tags WHERE id IN ({})".format(",".join("?" * len(tag_ids_list))),
            tag_ids_list,
        )
    }
    missing = sorted({tid for tid in tag_ids_list if tid not in existing_ids})
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unknown tag_ids: {missing}",
        )


async def _resolve_patch_tag_ids(
    db: aiosqlite.Connection,
    payload: SessionUpdate,
    fs: set[str],
) -> tuple[int, ...] | None:
    """Validate and return the patched tag_ids, or None when not in the payload."""
    if "tag_ids" not in fs or payload.tag_ids is None:
        return None
    tag_ids_list = payload.tag_ids
    if tag_ids_list:
        await _check_tag_ids_exist(db, tag_ids_list)
    new_tag_ids = tuple(tag_ids_list)
    await _validate_tag_cardinality(db, new_tag_ids)
    return new_tag_ids


def _require_non_null_title(title: str | None) -> str:
    """Return *title* or raise 422 when it is ``None``."""
    if title is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="title must not be null",
        )
    return title


def _require_non_negative_budget(max_budget_usd: float | None) -> None:
    """Raise 422 when *max_budget_usd* is set to a negative value."""
    if max_budget_usd is not None and max_budget_usd < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="max_budget_usd must be ≥ 0",
        )


def _build_patch_kwargs(
    payload: SessionUpdate,
    fs: set[str],
) -> dict[str, object]:
    """Build the update_fields kwargs dict from the patch payload's set fields."""
    kwargs: dict[str, object] = {}
    if "title" in fs:
        kwargs["title"] = _require_non_null_title(payload.title)
    if "description" in fs:
        kwargs["description"] = payload.description
    if "max_budget_usd" in fs:
        _require_non_negative_budget(payload.max_budget_usd)
        kwargs["max_budget_usd"] = payload.max_budget_usd
    if "session_instructions" in fs:
        kwargs["session_instructions"] = payload.session_instructions
    return kwargs


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.patch(
    "/api/sessions/{session_id}",
    response_model=SessionOut,
    operation_id="patch-session",
)
async def patch_session(
    session_id: str,
    payload: SessionUpdate,
    request: Request,
) -> SessionOut:
    """Full-field PATCH for a session (gap-cycle-10-001).

    Accepts any subset of ``title``, ``description``, ``max_budget_usd``,
    ``session_instructions``, and ``tag_ids``.  When ``tag_ids`` is present
    the session's tag set is replaced wholesale.
    """
    db = _db(request)
    fs = payload.model_fields_set
    new_tag_ids = await _resolve_patch_tag_ids(db, payload, fs)
    try:
        row = await sessions_db.update_fields(db, session_id, **_build_patch_kwargs(payload, fs))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    if new_tag_ids is not None:
        await tags_db.set_for_session(db, session_id=session_id, tag_ids=new_tag_ids)
    tags = await _fetch_tags_out(db, session_id)
    out = _to_out(row, tags=tags)
    broadcaster = _sessions_broadcaster(request)
    if broadcaster is not None:
        broadcaster.publish_upsert(out)
    return out


@router.patch(
    "/api/sessions/{session_id}/model",
    response_model=SessionOut,
    operation_id="patch-session-model",
)
async def patch_session_model(
    session_id: str,
    payload: SessionModelUpdate,
    request: Request,
) -> SessionOut:
    """Swap the session's executor model (spec §7; arch §1.1.5).

    Persists the new model name on the session row, then recycles the
    live SDK supervisor via :meth:`InProcessRunnerRegistry.recycle`.
    422 on unknown model names.
    """
    db = _db(request)
    try:
        row = await sessions_db.update_model(db, session_id, model=payload.model)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    factory = getattr(request.app.state, "runner_factory", None)
    if isinstance(factory, InProcessRunnerRegistry):
        await factory.recycle(session_id)
    tags = await _fetch_tags_out(db, session_id)
    out = _to_out(row, tags=tags)
    broadcaster = _sessions_broadcaster(request)
    if broadcaster is not None:
        broadcaster.publish_upsert(out)
    return out


@router.patch(
    "/api/sessions/{session_id}/permission_mode",
    response_model=SessionOut,
    operation_id="patch-session-permission-mode",
)
async def patch_session_permission_mode(
    session_id: str,
    payload: SessionPermissionModeUpdate,
    request: Request,
) -> SessionOut:
    """Swap the session's permission mode mid-session (item 3.3).

    ``None`` clears the column; the runner falls back to the profile
    default on next boot.  422 on unknown mode strings.
    """
    db = _db(request)
    try:
        row = await sessions_db.update_permission_mode(
            db, session_id, permission_mode=payload.permission_mode
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
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


@router.patch(
    "/api/sessions/{session_id}/pinned",
    response_model=SessionOut,
    operation_id="patch-session-pinned",
)
async def patch_session_pinned(
    session_id: str,
    payload: SessionPinnedUpdate,
    request: Request,
) -> SessionOut:
    """Pin or unpin a session row.  Idempotent; 404 when absent."""
    db = _db(request)
    row = await sessions_db.update_pinned(db, session_id, pinned=payload.pinned)
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
