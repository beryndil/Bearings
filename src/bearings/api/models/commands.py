"""Slash-command palette DTOs (commands + skills surfaced in the
textarea popup)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CommandOut(BaseModel):
    """One entry in the slash-command palette (command or skill).

    `slug` is the token inserted into the textarea without the leading
    `/` — it matches what the Claude Code CLI accepts (e.g. `fad:ship`,
    `pr-review-toolkit:review-pr`). `scope` records where the entry came
    from so the UI can group or badge it; `source_path` is kept for
    debugging only — the client should not display it.
    """

    slug: str
    description: str
    kind: Literal["command", "skill"]
    scope: Literal["user", "project", "plugin"]
    source_path: str


class CommandsListOut(BaseModel):
    entries: list[CommandOut]
