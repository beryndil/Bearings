# mypy: disable-error-code=explicit-any
"""Pydantic wire shapes for ``routes/shell.py`` (item 1.10)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from bearings.config.constants import (
    SHELL_ARGV_ENTRY_MAX_LENGTH,
    SHELL_ARGV_MAX_ENTRIES,
)


class ShellExecIn(BaseModel):
    """Request body for ``POST /api/shell/exec``."""

    model_config = ConfigDict(extra="forbid")

    argv: list[str] = Field(
        min_length=1,
        max_length=SHELL_ARGV_MAX_ENTRIES,
        description=(
            f"argv to dispatch (1-{SHELL_ARGV_MAX_ENTRIES} entries; "
            f"each entry ≤ {SHELL_ARGV_ENTRY_MAX_LENGTH} chars). "
            "argv[0] must be a member of the per-app shell allowlist."
        ),
    )


class ShellExecOut(BaseModel):
    """Response body for ``POST /api/shell/exec``."""

    model_config = ConfigDict(extra="forbid")

    exit_code: int
    reason: str
    stdout: str
    stderr: str
    duration_s: float


__all__ = ["ShellExecIn", "ShellExecOut"]
