# mypy: disable-error-code=explicit-any
"""Artifact registration + serve routes.

An artifact is a file path (local or remote) associated with a session.
The endpoint surface:

* ``POST   /api/artifacts``         — register an artifact.
* ``GET    /api/artifacts/{id}``    — serve the file (Content-Disposition: inline).
* ``DELETE /api/artifacts/{id}``    — unregister + remove local file.

``GET`` serves the raw bytes from the on-disk path when the path is an
absolute local file.  Remote URLs (``http://…`` / ``https://…``) are not
proxied in v1 — the client receives the artifact row without byte content.
If the file is absent the route returns 404.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from bearings.config.constants import (
    ARTIFACT_MIME_TYPE_MAX_LENGTH,
    ARTIFACT_PATH_MAX_LENGTH,
)
from bearings.db import artifacts as artifacts_db
from bearings.db import sessions as sessions_db
from bearings.db.artifacts import ArtifactRow
from bearings.web.routes._deps import _db

_LOG = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------


class ArtifactIn(BaseModel):
    """Request body for POST /api/artifacts."""

    session_id: str = Field(
        min_length=1,
        description="ID of the session this artifact belongs to.",
    )
    path: str = Field(
        min_length=1,
        max_length=ARTIFACT_PATH_MAX_LENGTH,
        description="Absolute local file path or remote URL.",
    )
    mime_type: str = Field(
        min_length=1,
        max_length=ARTIFACT_MIME_TYPE_MAX_LENGTH,
        description="MIME type of the artifact (e.g. image/png, application/pdf).",
    )


class ArtifactOut(BaseModel):
    """Wire representation of a registered artifact."""

    id: str
    session_id: str
    path: str
    mime_type: str
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_out(row: ArtifactRow) -> ArtifactOut:
    return ArtifactOut(
        id=row.id,
        session_id=row.session_id,
        path=row.path,
        mime_type=row.mime_type,
        created_at=row.created_at,
    )


def _is_local_path(path: str) -> bool:
    """Return True when ``path`` looks like an absolute local filesystem path."""
    return path.startswith("/") and not path.startswith("//")


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.post(
    "/api/artifacts",
    response_model=ArtifactOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="create-artifact",
    summary="Register an artifact against a session",
)
async def create_artifact(body: ArtifactIn, request: Request) -> ArtifactOut:
    """Register *path* as an artifact for *session_id*.

    Returns 404 when the referenced session does not exist.
    Returns 201 with the new artifact row on success.
    """
    db = _db(request)
    session = await sessions_db.get(db, body.session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session {body.session_id!r} not found",
        )
    row = await artifacts_db.create(
        db,
        session_id=body.session_id,
        path=body.path,
        mime_type=body.mime_type,
    )
    await db.commit()
    return _to_out(row)


@router.get(
    "/api/artifacts/{artifact_id}",
    operation_id="get-artifact",
    summary="Serve an artifact file",
)
async def get_artifact(
    artifact_id: str,
    request: Request,
) -> FileResponse:
    """Return the artifact file with ``Content-Disposition: inline``.

    Returns 404 when the artifact is not registered or the local file is
    absent.  Remote URLs are not proxied — use the registration row's
    ``path`` field directly.
    """
    db = _db(request)
    row = await artifacts_db.get(db, artifact_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"artifact {artifact_id!r} not found",
        )
    if not _is_local_path(row.path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Remote-URL artifacts cannot be served via this endpoint.",
        )
    local_path = Path(row.path)
    if not local_path.is_file():  # noqa: ASYNC240
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"artifact file not found on disk: {row.path!r}",
        )
    return FileResponse(
        path=str(local_path),
        media_type=row.mime_type,
        headers={"Content-Disposition": "inline"},
    )


@router.delete(
    "/api/artifacts/{artifact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete-artifact",
    summary="Unregister and delete an artifact",
)
async def delete_artifact(artifact_id: str, request: Request) -> None:
    """Remove the artifact registration and delete the file if local.

    Returns 404 when the artifact is not registered.
    """
    db = _db(request)
    row = await artifacts_db.get(db, artifact_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"artifact {artifact_id!r} not found",
        )
    deleted = await artifacts_db.delete(db, artifact_id)
    if not deleted:
        _LOG.warning("delete_artifact: expected to delete %r but rowcount=0", artifact_id)
    await db.commit()

    # Best-effort local file removal.  If the file is absent (already removed
    # by the user or another process) we log and continue — the registration
    # is gone so the artifact is effectively cleaned up.
    if _is_local_path(row.path):
        local_path = Path(row.path)
        if local_path.is_file():  # noqa: ASYNC240
            try:
                local_path.unlink()  # noqa: ASYNC240
            except OSError as exc:
                _LOG.warning("delete_artifact: could not remove %r: %s", row.path, exc)


__all__ = ["router"]
