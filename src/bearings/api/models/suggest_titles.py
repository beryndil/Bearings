"""DTO surface for the auto-suggest-titles plan
(`~/.claude/plans/auto-suggesting-titles.md`).

Only one shape: the response body for
`POST /sessions/{id}/suggest_titles`. There's no request body — the
session id in the path is the entire input. Kept in its own module
so the public DTO surface stays grouped by feature, matching the
`reorg`, `tags`, etc. layout siblings."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SuggestTitlesResult(BaseModel):
    """Response from `POST /sessions/{id}/suggest_titles`. Always
    exactly three candidates on success — the suggester rejects
    shorter responses upstream so the UI can render a fixed three-pill
    row without a length check. Order is narrow → medium → wide
    abstraction levels per the system-prompt instruction."""

    titles: list[str] = Field(min_length=3, max_length=3)
