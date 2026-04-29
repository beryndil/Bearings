"""Filesystem-walk routes (item 1.10).

Per ``docs/architecture-v1.md`` §1.1.5 ``web/routes/fs.py`` is the
general-purpose FS picker (distinct from the plan/todo-only vault
index per ``docs/behavior/vault.md``):

* ``GET /api/fs/list?path=<abs>`` — directory entries.
* ``GET /api/fs/read?path=<abs>`` — utf-8 text body.

Both endpoints validate paths through
:func:`bearings.agent.fs.validate_path` (realpath resolution +
allow-roots boundary check) before opening anything. The contract
rejects relative paths at the boundary; ``..`` and symlink escapes
collapse during ``Path.resolve`` and are caught by the allow-roots
check.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status

from bearings.agent.fs import (
    FsValidationError,
    list_dir,
    read_text,
    validate_path,
)
from bearings.config.settings import FsCfg
from bearings.web.models.fs import FsEntryOut, FsListOut, FsReadOut

router = APIRouter()


def _cfg(request: Request) -> FsCfg:
    """Pull the :class:`FsCfg` off ``app.state``; falls back to defaults."""
    cfg = getattr(request.app.state, "fs_cfg", None)
    if cfg is None:
        return FsCfg()
    if not isinstance(cfg, FsCfg):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="fs_cfg on app.state is not an FsCfg instance",
        )
    return cfg


@router.get("/api/fs/list", response_model=FsListOut)
async def get_list(
    request: Request,
    path: str = Query(..., description="Absolute path to list."),
) -> FsListOut:
    """List a directory under one of the configured allow-roots."""
    cfg = _cfg(request)
    try:
        resolved = validate_path(path, cfg.allow_roots)
        listing = list_dir(resolved, cfg.list_max_entries)
    except FsValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return FsListOut(
        path=listing.path,
        entries=[
            FsEntryOut(
                name=e.name,
                kind=e.kind,
                size=e.size,
                mtime=e.mtime,
                is_readable=e.is_readable,
            )
            for e in listing.entries
        ],
        capped=listing.capped,
    )


@router.get("/api/fs/read", response_model=FsReadOut)
async def get_read(
    request: Request,
    path: str = Query(..., description="Absolute path to read as utf-8 text."),
) -> FsReadOut:
    """Read a file's content as utf-8 text under one of the allow-roots."""
    cfg = _cfg(request)
    try:
        resolved = validate_path(path, cfg.allow_roots)
        result = read_text(resolved, cfg.read_max_bytes)
    except FsValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return FsReadOut(
        path=result.path,
        content=result.content,
        size=result.size,
        truncated=result.truncated,
    )


__all__ = ["router"]
