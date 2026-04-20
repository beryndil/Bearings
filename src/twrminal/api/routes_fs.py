"""Filesystem listing for the folder-picker UI.

Lists directories under an absolute path so the FolderPicker can walk
the tree without relying on a browser-side file dialog (which can't
access server-side paths). Read-only; no write or execute semantics.

Security posture: Twrminal binds 127.0.0.1 by default and is a
single-user tool. Exposing directory names to the local browser is
equivalent to the user running `ls` in a terminal — not a meaningful
disclosure.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from twrminal.api.auth import require_auth
from twrminal.api.models import FsEntryOut, FsListOut

router = APIRouter(
    prefix="/fs",
    tags=["fs"],
    dependencies=[Depends(require_auth)],
)


def _list_dir(path: Path, *, hidden: bool) -> FsListOut:
    """Assemble an FsListOut for an already-resolved directory. Caller
    is responsible for validating that `path` exists and is a dir."""
    entries: list[FsEntryOut] = []
    for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if not hidden and child.name.startswith("."):
            continue
        if not child.is_dir():
            continue
        entries.append(FsEntryOut(name=child.name, path=str(child)))
    parent = str(path.parent) if path.parent != path else None
    return FsListOut(path=str(path), parent=parent, entries=entries)


@router.get("/list", response_model=FsListOut)
async def list_dir(path: str | None = None, hidden: bool = False) -> FsListOut:
    target = Path(path) if path else Path.home()
    if not target.is_absolute():
        raise HTTPException(status_code=400, detail="path must be absolute")
    try:
        resolved = target.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=404, detail="path not found") from exc
    if not resolved.is_dir():
        raise HTTPException(status_code=404, detail="path is not a directory")
    try:
        return _list_dir(resolved, hidden=hidden)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="permission denied") from exc
