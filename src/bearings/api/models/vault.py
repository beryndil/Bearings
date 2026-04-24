"""Vault DTOs: plan/todo index, full-doc fetch, and search hits."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class VaultEntryOut(BaseModel):
    """One row in the vault index. `kind` is the source bucket
    (`'plan'` under `vault.plan_roots`, `'todo'` from
    `vault.todo_globs`); `slug` is the filename stem — plans share
    their stem with the session they describe, so the frontend can
    cross-link on this value."""

    path: str
    kind: Literal["plan", "todo"]
    slug: str
    title: str | None = None
    mtime: float
    size: int


class VaultIndexOut(BaseModel):
    """Snapshot of every vault-visible doc at request time. Each
    bucket is sorted newest-first so the UI can render mtime groups
    (Today / This week / Older) without re-sorting on the client."""

    plans: list[VaultEntryOut]
    todos: list[VaultEntryOut]


class VaultDocOut(BaseModel):
    """Full body of a single vault doc. `body` is raw markdown; the
    frontend runs it through the same `marked + shiki` pipeline the
    chat turns use."""

    path: str
    kind: Literal["plan", "todo"]
    slug: str
    title: str | None = None
    mtime: float
    size: int
    body: str


class VaultSearchHit(BaseModel):
    """Single matched line in a vault doc. `snippet` is the matched
    line trimmed — caller can render it verbatim without additional
    processing."""

    path: str
    line: int
    snippet: str


class VaultSearchOut(BaseModel):
    """Results of `/api/vault/search`. `truncated` signals the cap
    was hit — the UI can show a 'narrow your query' hint rather than
    implying zero further matches."""

    query: str
    hits: list[VaultSearchHit]
    truncated: bool = False
