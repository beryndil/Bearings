"""Slash-command palette endpoint.

Returns every command/skill the user could type after `/` in the
composer: user-level, project-level (when a `cwd` is supplied), and
plugin-level entries from installed marketplaces. Pure filesystem read
— no DB, no write side. Security posture matches `routes_fs`: Bearings
binds 127.0.0.1 by default and this is equivalent to running
`ls ~/.claude/commands` in a terminal.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from bearings.api import commands_scan
from bearings.api.auth import require_auth
from bearings.api.models import CommandsListOut

router = APIRouter(
    prefix="/commands",
    tags=["commands"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=CommandsListOut)
async def list_commands(cwd: str | None = None) -> CommandsListOut:
    """List available slash commands and skills.

    `cwd` (optional) — absolute path to the session's working directory.
    When present, its `.claude/commands` and `.claude/skills` trees are
    scanned at project scope with highest precedence over colliding
    slugs from user/plugin scope.
    """
    project_cwd: Path | None = None
    if cwd is not None:
        candidate = Path(cwd)
        if not candidate.is_absolute():
            raise HTTPException(status_code=400, detail="cwd must be absolute")
        # Silently ignore a missing cwd — sessions can outlive their
        # project directory; the palette should still return user/plugin
        # entries instead of 404'ing the whole request.
        if candidate.is_dir():
            project_cwd = candidate

    entries = commands_scan.collect(home=Path.home(), project_cwd=project_cwd)
    return CommandsListOut(entries=entries)
