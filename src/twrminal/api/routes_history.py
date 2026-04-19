from __future__ import annotations

from datetime import date as date_cls
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from twrminal.api.auth import require_auth
from twrminal.api.models import SearchHit
from twrminal.db import store

router = APIRouter(
    prefix="/history",
    tags=["history"],
    dependencies=[Depends(require_auth)],
)

SNIPPET_MAX = 160


def _snippet(text: str, query: str) -> str:
    """Trim to a ~160-char window around the first case-insensitive
    match. Matches `LIKE %q%` behavior; if the source is `thinking`
    or the match is in it, the caller still wins because we feed
    whichever field yielded the hit."""
    if not text:
        return ""
    lower = text.lower()
    idx = lower.find(query.lower())
    if idx < 0:
        return text[:SNIPPET_MAX] + ("…" if len(text) > SNIPPET_MAX else "")
    start = max(0, idx - 40)
    end = min(len(text), idx + len(query) + 120)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def _validate_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        date_cls.fromisoformat(value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="invalid date (YYYY-MM-DD)") from e
    return value


async def _dump(request: Request, *, date_from: str | None, date_to: str | None) -> dict[str, Any]:
    conn = request.app.state.db
    return {
        "sessions": await store.list_all_sessions(conn, date_from=date_from, date_to=date_to),
        "messages": await store.list_all_messages(conn, date_from=date_from, date_to=date_to),
        "tool_calls": await store.list_all_tool_calls(conn, date_from=date_from, date_to=date_to),
    }


@router.get("/export")
async def export_history(
    request: Request,
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
) -> dict[str, Any]:
    return await _dump(
        request,
        date_from=_validate_date(date_from),
        date_to=_validate_date(date_to),
    )


@router.get("/daily/{date}")
async def daily_log(date: str, request: Request) -> dict[str, Any]:
    validated = _validate_date(date)
    return await _dump(request, date_from=validated, date_to=validated)


@router.get("/search", response_model=list[SearchHit])
async def search_history(
    request: Request,
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=500),
) -> list[SearchHit]:
    rows = await store.search_messages(request.app.state.db, q, limit=limit)
    hits: list[SearchHit] = []
    for row in rows:
        # Prefer content for the snippet — fall back to thinking when
        # the match is only there.
        content = row.get("content") or ""
        thinking = row.get("thinking") or ""
        source = content if q.lower() in content.lower() else thinking
        hits.append(
            SearchHit(
                message_id=row["message_id"],
                session_id=row["session_id"],
                session_title=row.get("session_title"),
                model=row["model"],
                role=row["role"],
                snippet=_snippet(source, q),
                created_at=row["created_at"],
            )
        )
    return hits
