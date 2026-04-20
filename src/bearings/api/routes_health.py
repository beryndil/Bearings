from __future__ import annotations

from fastapi import APIRouter, Request

from bearings import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    enabled = request.app.state.settings.auth.enabled
    return {
        "auth": "required" if enabled else "disabled",
        "version": __version__,
    }
