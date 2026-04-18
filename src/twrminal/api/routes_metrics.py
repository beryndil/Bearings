from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

router = APIRouter(tags=["metrics"])

_REGISTRY = CollectorRegistry()


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(_REGISTRY), media_type=CONTENT_TYPE_LATEST)
