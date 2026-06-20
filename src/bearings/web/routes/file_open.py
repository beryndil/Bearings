"""File open handler — opens files/directories in system file manager.

Provides HTTP endpoints for Claude Code sessions to open local files
in the default file manager (Thunar, Dolphin, Nautilus, etc.) via
clickable links.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

__all__ = ["router"]

router = APIRouter(prefix="/api/file-open", tags=["file-open"])


class FileOpenRequest(BaseModel):
    """Request to open a file or directory."""

    path: str = Field(..., description="Absolute path to file or directory")


@router.post("/", summary="Open file or directory in system file manager")
async def open_file(request: FileOpenRequest) -> dict[str, str]:
    """Open a file or directory in the default system file manager.

    Args:
        request: FileOpenRequest with absolute path

    Returns:
        Status dict with success message

    Raises:
        HTTPException: If path does not exist or is not accessible
    """
    try:
        # Expand ~ and resolve to absolute path
        path = Path(request.path).expanduser().resolve()

        # Verify path exists
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Path not found: {path}")

        # If it's a file, open its directory
        if path.is_file():
            open_path = path.parent
        else:
            open_path = path

        # Use systemd-run to open in the user's session context
        # This ensures it runs with proper display/wayland environment
        subprocess.Popen(
            ["systemd-run", "--user", "--scope", "thunar", str(open_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return {
            "status": "opened",
            "path": str(open_path),
            "type": "directory" if open_path.is_dir() else "file",
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
