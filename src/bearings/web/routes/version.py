# mypy: disable-error-code=explicit-any
"""Version endpoint — ``GET /api/version`` (N-14).

Returns the build mtime of the static UI bundle so the frontend
``versionWatcher`` can detect when a new bundle has been deployed and
trigger a page reload.

The mtime is the Unix timestamp (seconds, float) of the newest file
in the ``web/dist/`` bundle directory.  When the directory does not
exist (e.g. a fresh checkout without a built bundle), the mtime is
reported as ``0.0`` — the frontend treats any newer server mtime as
"reload needed" against the stored page-load mtime, so a zero base
means the first check will always appear "newer" and trigger a reload
after a dist directory appears.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# The static bundle lives next to this package's parent (web/).
_DIST_DIR = Path(__file__).parent.parent / "dist"


def _bundle_mtime() -> float:
    """Return the mtime of the newest file in ``web/dist/``.

    Walks the directory tree; returns 0.0 when the directory does
    not exist or is empty.
    """
    if not _DIST_DIR.is_dir():
        return 0.0
    newest: float = 0.0
    for dirpath, _dirnames, filenames in os.walk(_DIST_DIR):
        for filename in filenames:
            try:
                mtime = os.path.getmtime(os.path.join(dirpath, filename))
                if mtime > newest:
                    newest = mtime
            except OSError:
                pass
    return newest


class VersionOut(BaseModel):
    """Response shape for ``GET /api/version``."""

    bundle_mtime: float


@router.get(
    "/api/version",
    response_model=VersionOut,
    operation_id="get-version",
    summary="Get the build mtime of the static UI bundle",
    description=(
        "Returns the Unix timestamp (float seconds) of the newest file "
        "in the ``web/dist/`` bundle directory. The frontend polls this "
        "endpoint to detect hot-deployed bundle updates and auto-reload "
        "on idle or ``visibilitychange`` when the server mtime is newer "
        "than the mtime captured at page load."
    ),
)
async def get_version() -> VersionOut:
    """Return the bundle mtime for the frontend version watcher."""
    return VersionOut(bundle_mtime=_bundle_mtime())


__all__ = ["router"]
