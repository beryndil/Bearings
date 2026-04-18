from __future__ import annotations

from fastapi import APIRouter

from twrminal import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"auth": "unknown", "version": __version__}
