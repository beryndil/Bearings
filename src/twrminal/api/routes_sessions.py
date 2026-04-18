from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
async def list_sessions() -> dict[str, str]:
    raise HTTPException(status_code=501, detail="not implemented")


@router.post("")
async def create_session() -> dict[str, str]:
    raise HTTPException(status_code=501, detail="not implemented")


@router.get("/{session_id}")
async def get_session(session_id: str) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="not implemented")


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="not implemented")
