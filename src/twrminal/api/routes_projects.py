from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from twrminal.api.auth import require_auth
from twrminal.api.models import ProjectCreate, ProjectOut, ProjectUpdate
from twrminal.db import store

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[ProjectOut])
async def list_projects(request: Request) -> list[ProjectOut]:
    rows = await store.list_projects(request.app.state.db)
    return [ProjectOut(**r) for r in rows]


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, request: Request) -> ProjectOut:
    try:
        row = await store.create_project(
            request.app.state.db,
            name=body.name,
            description=body.description,
            system_prompt=body.system_prompt,
            working_dir=body.working_dir,
            default_model=body.default_model,
            pinned=body.pinned,
            sort_order=body.sort_order,
        )
    except Exception as exc:  # aiosqlite raises IntegrityError on UNIQUE
        if "UNIQUE" in str(exc):
            raise HTTPException(status_code=409, detail="project name already exists") from exc
        raise
    return ProjectOut(**row)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, request: Request) -> ProjectOut:
    row = await store.get_project(request.app.state.db, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    return ProjectOut(**row)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, body: ProjectUpdate, request: Request) -> ProjectOut:
    # Only fields the client explicitly set are applied — unset fields
    # leave the column untouched, explicit null clears it.
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    try:
        row = await store.update_project(request.app.state.db, project_id, fields=fields)
    except Exception as exc:
        if "UNIQUE" in str(exc):
            raise HTTPException(status_code=409, detail="project name already exists") from exc
        raise
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    return ProjectOut(**row)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, request: Request) -> Response:
    # Deletion is ON DELETE SET NULL on sessions.project_id — sessions
    # survive, they just lose their project assignment (per v0.2 spec).
    ok = await store.delete_project(request.app.state.db, project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="project not found")
    return Response(status_code=204)
