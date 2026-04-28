# mypy: disable-error-code=explicit-any
"""Pydantic wire shapes for ``routes/vault.py``.

Per ``docs/architecture-v1.md`` §1.1.5 the wire DTOs live alongside
the route module. The shapes mirror :class:`bearings.db.vault.VaultEntry`
+ :class:`bearings.agent.vault.SearchHit` /
:class:`bearings.agent.vault.SearchResult` /
:class:`bearings.agent.vault.Redaction` row dataclasses; the route
constructs an ``Out`` model from a row dataclass at the wire boundary.

The ``mypy: disable-error-code=explicit-any`` pragma matches the same
narrow carve-out :mod:`bearings.web.models.tags` makes for Pydantic's
metaclass-exposed ``Any`` surface.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class VaultEntryOut(BaseModel):
    """Response shape for a single vault row.

    Per ``docs/behavior/vault.md`` §"When the user opens the vault"
    each row carries an absolute path, slug, optional title, kind,
    mtime, and size; per §"Paste-into-message behavior" the
    ``markdown_link`` field is server-computed so the client doesn't
    have to assemble it (matches the ``group`` server-computed field
    pattern on :class:`bearings.web.models.tags.TagOut`).
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    path: str
    slug: str
    title: str | None
    kind: str
    mtime: int
    size: int
    last_indexed_at: int
    markdown_link: str


class VaultListOut(BaseModel):
    """Response shape for ``GET /api/vault`` — bucketed list.

    Per vault.md §"When the user opens the vault" the user sees a
    Plans section and a Todos section; the wire surfaces both
    buckets as separate arrays so the client doesn't have to filter
    on the wire-side ``kind`` discriminator. ``plan_roots`` /
    ``todo_globs`` mirror the configured paths so the empty-state
    UI ("No plans found under …") can name them per vault.md
    §"When the user opens the vault" → empty state.
    """

    model_config = ConfigDict(extra="forbid")

    plans: list[VaultEntryOut]
    todos: list[VaultEntryOut]
    plan_roots: list[str]
    todo_globs: list[str]


class RedactionOut(BaseModel):
    """One redaction range. Mirrors :class:`bearings.agent.vault.Redaction`."""

    model_config = ConfigDict(extra="forbid")

    offset: int
    length: int
    pattern: str


class VaultDocOut(BaseModel):
    """Response shape for ``GET /api/vault/{id}`` — entry + body + redactions.

    Per vault.md §"Redaction rendering" the server returns the raw
    body plus a list of redaction ranges; the client masks visually
    and toggles per-range. ``persists no toggle state`` — the server
    re-detects on every fetch (so a file edited to remove a secret
    surfaces unredacted on the next read).
    """

    model_config = ConfigDict(extra="forbid")

    entry: VaultEntryOut
    body: str
    redactions: list[RedactionOut]
    truncated: bool


class SearchHitOut(BaseModel):
    """One search hit row. Mirrors :class:`bearings.agent.vault.SearchHit`."""

    model_config = ConfigDict(extra="forbid")

    vault_id: int
    path: str
    title: str | None
    kind: str
    line_number: int
    snippet: str


class SearchResultOut(BaseModel):
    """Response shape for ``GET /api/vault/search``.

    ``capped`` reflects the "showing first N — narrow your query for
    more" indicator from vault.md §"Search semantics".
    """

    model_config = ConfigDict(extra="forbid")

    hits: list[SearchHitOut]
    capped: bool


__all__ = [
    "RedactionOut",
    "SearchHitOut",
    "SearchResultOut",
    "VaultDocOut",
    "VaultEntryOut",
    "VaultListOut",
]
