from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/export")
async def export_history() -> dict[str, str]:
    raise HTTPException(status_code=501, detail="not implemented")


@router.get("/daily/{date}")
async def daily_log(date: str) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="not implemented")
