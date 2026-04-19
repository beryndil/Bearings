from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from twrminal.api.auth import require_auth
from twrminal.api.models import TagCreate, TagOut, TagUpdate
from twrminal.db import store

router = APIRouter(
    prefix="/tags",
    tags=["tags"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[TagOut])
async def list_tags(request: Request) -> list[TagOut]:
    rows = await store.list_tags(request.app.state.db)
    return [TagOut(**r) for r in rows]


@router.post("", response_model=TagOut, status_code=201)
async def create_tag(body: TagCreate, request: Request) -> TagOut:
    try:
        row = await store.create_tag(
            request.app.state.db,
            name=body.name,
            color=body.color,
            pinned=body.pinned,
            sort_order=body.sort_order,
        )
    except Exception as exc:  # aiosqlite raises IntegrityError on UNIQUE
        if "UNIQUE" in str(exc):
            raise HTTPException(status_code=409, detail="tag name already exists") from exc
        raise
    return TagOut(**row)


@router.get("/{tag_id}", response_model=TagOut)
async def get_tag(tag_id: int, request: Request) -> TagOut:
    row = await store.get_tag(request.app.state.db, tag_id)
    if row is None:
        raise HTTPException(status_code=404, detail="tag not found")
    return TagOut(**row)


@router.patch("/{tag_id}", response_model=TagOut)
async def update_tag(tag_id: int, body: TagUpdate, request: Request) -> TagOut:
    # Only fields the client explicitly set are applied — unset fields
    # leave the column untouched.
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    try:
        row = await store.update_tag(request.app.state.db, tag_id, fields=fields)
    except Exception as exc:
        if "UNIQUE" in str(exc):
            raise HTTPException(status_code=409, detail="tag name already exists") from exc
        raise
    if row is None:
        raise HTTPException(status_code=404, detail="tag not found")
    return TagOut(**row)


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(tag_id: int, request: Request) -> Response:
    ok = await store.delete_tag(request.app.state.db, tag_id)
    if not ok:
        raise HTTPException(status_code=404, detail="tag not found")
    return Response(status_code=204)
