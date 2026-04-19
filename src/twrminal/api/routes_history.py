from __future__ import annotations

from datetime import date as date_cls
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from twrminal.db import store

router = APIRouter(prefix="/history", tags=["history"])


async def _dump(request: Request, date_prefix: str | None) -> dict[str, Any]:
    conn = request.app.state.db
    return {
        "sessions": await store.list_all_sessions(conn, date_prefix=date_prefix),
        "messages": await store.list_all_messages(conn, date_prefix=date_prefix),
        "tool_calls": await store.list_all_tool_calls(conn, date_prefix=date_prefix),
    }


@router.get("/export")
async def export_history(request: Request) -> dict[str, Any]:
    return await _dump(request, None)


@router.get("/daily/{date}")
async def daily_log(date: str, request: Request) -> dict[str, Any]:
    try:
        date_cls.fromisoformat(date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="invalid date (YYYY-MM-DD)") from e
    return await _dump(request, date)
