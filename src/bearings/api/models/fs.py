"""Filesystem browsing / picking / upload DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class FsEntryOut(BaseModel):
    """One row in an FsListOut. `is_dir` is always present — it's True
    for directories and False for files — so the in-app file picker can
    distinguish "descend here" from "select this file" without a second
    round-trip. FolderPicker ignores the flag and keeps listing dirs
    only via `include_files=false`."""

    name: str
    path: str
    is_dir: bool


class FsListOut(BaseModel):
    path: str
    parent: str | None
    entries: list[FsEntryOut]


class FsPickOut(BaseModel):
    """Result of POST /fs/pick. `path` is the absolute filesystem path
    the user chose (first pick when multi-select is on), or None when
    they cancelled the dialog. `paths` mirrors `path` for single-select
    and carries every pick when `multiple` is requested. `cancelled` is
    true iff the dialog was dismissed without a selection — a signal the
    UI uses to no-op silently rather than surface an error.
    """

    path: str | None
    paths: list[str]
    cancelled: bool


class UploadOut(BaseModel):
    """Result of `POST /api/uploads`. `path` is the absolute filesystem
    path the frontend injects into the prompt — Claude reads from that
    path exactly as if the user had typed it by hand. `filename` is the
    sanitized original name for optional UI display; the on-disk name
    is always a UUID so two drops of `screenshot.png` don't collide and
    traversal via the original name is impossible. `size_bytes` and
    `mime_type` round out the shape for a future attachment-chip
    renderer above the user bubble.
    """

    path: str
    filename: str
    size_bytes: int
    mime_type: str
