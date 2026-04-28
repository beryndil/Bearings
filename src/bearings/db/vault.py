"""``vault`` table queries — cache for the read-only filesystem index.

Per ``docs/architecture-v1.md`` §1.1.3 this concern module owns every
query that touches the ``vault`` table. Per
``docs/behavior/vault.md`` the vault is a read-only browser over the
user's on-disk planning markdown — plans (``.md`` directly under each
configured plan root) and todos (``TODO.md`` matched by configured
globs); the table itself is a *cache* of the live filesystem state, not
a storage layer the user writes to. Vault.md mandates "the vault
re-scans on every list request; mtimes always reflect the current
filesystem state" — the rescan path lives in :mod:`bearings.agent.vault`
and writes through :func:`replace_index` here.

Stable-id contract
------------------

The cache is upserted on the unique ``path`` column rather than
truncated-and-rebuilt on every rescan. Reasoning: the API surface
returns ``id``-keyed rows, and the user's UI keeps an ``id`` reference
between "list" and "open by id" calls. Truncate-and-rebuild would cycle
the AUTOINCREMENT counter on every rescan and break that handoff. The
upsert path preserves stable ids for unchanged paths; a path that
disappears from the filesystem is deleted from the cache (so its id
becomes invalid, which is the correct behavior — the doc no longer
exists).

Public surface:

* :class:`VaultEntry` — frozen dataclass row mirror with
  ``__post_init__`` validation.
* :func:`replace_index` — upsert N scanned docs by path + delete rows
  whose path is not in the scanned set; atomic at the SQLite-
  transaction level.
* :func:`list_all`, :func:`get`, :func:`get_by_path` — cache reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import aiosqlite

from bearings.config.constants import KNOWN_VAULT_KINDS


@dataclass(frozen=True)
class VaultEntry:
    """Row mirror for the ``vault`` table.

    Field semantics follow ``schema.sql``:

    * ``id`` — INTEGER PRIMARY KEY AUTOINCREMENT.
    * ``path`` — absolute filesystem path; UNIQUE across the table.
    * ``slug`` — basename without extension (e.g. ``foo`` for
      ``foo.md``); the user-visible row label fallback when ``title``
      is unset.
    * ``title`` — optional first ``# heading`` from the file body
      (per vault.md §"Vault entry types").
    * ``kind`` — one of :data:`bearings.config.constants.KNOWN_VAULT_KINDS`
      (``plan`` or ``todo``); pinned by the schema's CHECK.
    * ``mtime`` — filesystem modification time as unix seconds; the
      value the row was indexed with (re-read on every rescan per
      vault.md "the vault re-scans on every list request").
    * ``size`` — file size in bytes at index time.
    * ``last_indexed_at`` — unix-seconds wall-clock of the rescan
      that wrote this row.
    """

    id: int
    path: str
    slug: str
    title: str | None
    kind: str
    mtime: int
    size: int
    last_indexed_at: int

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("VaultEntry.path must be non-empty")
        if not self.slug:
            raise ValueError("VaultEntry.slug must be non-empty")
        if self.kind not in KNOWN_VAULT_KINDS:
            raise ValueError(f"VaultEntry.kind {self.kind!r} not in {sorted(KNOWN_VAULT_KINDS)}")
        if self.mtime < 0:
            raise ValueError(f"VaultEntry.mtime must be ≥ 0 (got {self.mtime})")
        if self.size < 0:
            raise ValueError(f"VaultEntry.size must be ≥ 0 (got {self.size})")
        if self.last_indexed_at < 0:
            raise ValueError(f"VaultEntry.last_indexed_at must be ≥ 0 (got {self.last_indexed_at})")


@dataclass(frozen=True)
class ScannedDoc:
    """Pre-DB shape produced by the agent-layer filesystem scan.

    The agent layer (:mod:`bearings.agent.vault`) walks plan roots and
    TODO globs and emits one of these per discovered file. The DB
    layer's :func:`replace_index` accepts a sequence of these and
    materialises them as :class:`VaultEntry` rows. Keeping the two
    types separate makes the boundary explicit: ``ScannedDoc`` knows
    nothing about row ids, ``VaultEntry`` carries the post-INSERT id.
    """

    path: str
    slug: str
    title: str | None
    kind: str
    mtime: int
    size: int


def _now_unix() -> int:
    """Current wall-clock as unix seconds (UTC).

    Inlined here rather than added to :mod:`bearings.db._id` because
    the rest of the rebuild's TEXT timestamp surfaces use ISO-8601;
    the vault table is the only ``bearings.db`` module writing INTEGER
    unix seconds. Adding a helper to ``_id.py`` would invite TEXT
    callers to mis-import it.
    """
    return int(datetime.now(tz=UTC).timestamp())


async def replace_index(
    connection: aiosqlite.Connection,
    scanned: list[ScannedDoc],
) -> list[VaultEntry]:
    """Replace the cache with ``scanned``: upsert by path + delete vanished.

    Atomic at the SQLite-transaction level. Steps:

    1. Compute ``last_indexed_at = now_unix()`` once for the batch.
    2. UPSERT each :class:`ScannedDoc` by its unique ``path`` —
       existing rows preserve their ``id`` and have their mutable
       fields (``slug``, ``title``, ``kind``, ``mtime``, ``size``,
       ``last_indexed_at``) refreshed; new rows get a fresh AUTOINCREMENT
       id.
    3. DELETE any pre-existing row whose ``path`` is not in
       ``scanned`` — these are docs that disappeared from the
       filesystem.
    4. Return the post-replace cache contents in (kind, mtime DESC)
       order — the same order vault.md mandates for the "list" view.

    Empty ``scanned`` is valid — every existing cache row is deleted
    and the function returns an empty list (the user's vault has been
    fully reset, e.g. they unconfigured every plan root).
    """
    indexed_at = _now_unix()
    paths_in_scan = [doc.path for doc in scanned]
    # Sanity-check kind values before the INSERT — a bad kind would
    # otherwise surface as a CHECK-constraint failure mid-transaction
    # and leave the cache in a partially-written state. Validating
    # here is cheap and keeps the error close to the bad input.
    for doc in scanned:
        if doc.kind not in KNOWN_VAULT_KINDS:
            raise ValueError(f"ScannedDoc.kind {doc.kind!r} not in {sorted(KNOWN_VAULT_KINDS)}")
    for doc in scanned:
        await connection.execute(
            "INSERT INTO vault (path, slug, title, kind, mtime, size, last_indexed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET "
            "slug = excluded.slug, "
            "title = excluded.title, "
            "kind = excluded.kind, "
            "mtime = excluded.mtime, "
            "size = excluded.size, "
            "last_indexed_at = excluded.last_indexed_at",
            (
                doc.path,
                doc.slug,
                doc.title,
                doc.kind,
                doc.mtime,
                doc.size,
                indexed_at,
            ),
        )
    # Delete rows whose path is no longer in the scan. Build the
    # IN-clause from a parameterised tuple so a path containing SQL
    # quote characters can't escape.
    if paths_in_scan:
        placeholders = ",".join("?" * len(paths_in_scan))
        await connection.execute(
            f"DELETE FROM vault WHERE path NOT IN ({placeholders})",
            tuple(paths_in_scan),
        )
    else:
        await connection.execute("DELETE FROM vault")
    await connection.commit()
    return await list_all(connection)


async def list_all(
    connection: aiosqlite.Connection,
    *,
    kind: str | None = None,
) -> list[VaultEntry]:
    """Every cache row, bucketed by kind, sorted newest-mtime first.

    Per vault.md §"When the user opens the vault" — "Plans section
    … sorted most-recent-mtime first … Todos section … also sorted
    most-recent-mtime first". The query orders by ``(kind ASC, mtime
    DESC)`` so plans group before todos and within each bucket the
    newest entry surfaces first. ``kind=None`` returns both buckets;
    a specific kind narrows to one.

    The order ``kind ASC`` puts ``'plan'`` before ``'todo'``
    alphabetically — matches the vault.md presentation order
    (Plans section, then Todos section).
    """
    if kind is not None:
        if kind not in KNOWN_VAULT_KINDS:
            raise ValueError(f"list_all kind {kind!r} not in {sorted(KNOWN_VAULT_KINDS)}")
        cursor = await connection.execute(
            _SELECT_VAULT_COLUMNS + " WHERE kind = ? ORDER BY mtime DESC, path ASC",
            (kind,),
        )
    else:
        cursor = await connection.execute(
            _SELECT_VAULT_COLUMNS + " ORDER BY kind ASC, mtime DESC, path ASC"
        )
    try:
        rows = await cursor.fetchall()
    finally:
        await cursor.close()
    return [_row_to_entry(row) for row in rows]


async def get(connection: aiosqlite.Connection, vault_id: int) -> VaultEntry | None:
    """Fetch a single cache row by id; ``None`` if no such row."""
    cursor = await connection.execute(
        _SELECT_VAULT_COLUMNS + " WHERE id = ?",
        (vault_id,),
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    return None if row is None else _row_to_entry(row)


async def get_by_path(
    connection: aiosqlite.Connection,
    path: str,
) -> VaultEntry | None:
    """Fetch a single cache row by its UNIQUE absolute ``path``.

    Used by the API layer's path-safety gate (vault.md §"Failure
    modes" — "Path outside the vault. Attempts … to open a path
    that is not in the current index are refused"). The caller
    resolves any symlinks before calling so a symlink trick into the
    vault still resolves to the real path and is gated correctly.
    """
    cursor = await connection.execute(
        _SELECT_VAULT_COLUMNS + " WHERE path = ?",
        (path,),
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    return None if row is None else _row_to_entry(row)


_SELECT_VAULT_COLUMNS = (
    "SELECT id, path, slug, title, kind, mtime, size, last_indexed_at FROM vault"
)


def _row_to_entry(row: aiosqlite.Row | tuple[object, ...]) -> VaultEntry:
    """Translate a raw SELECT tuple to a validated :class:`VaultEntry`."""
    return VaultEntry(
        id=int(str(row[0])),
        path=str(row[1]),
        slug=str(row[2]),
        title=None if row[3] is None else str(row[3]),
        kind=str(row[4]),
        mtime=int(str(row[5])),
        size=int(str(row[6])),
        last_indexed_at=int(str(row[7])),
    )


__all__ = [
    "ScannedDoc",
    "VaultEntry",
    "get",
    "get_by_path",
    "list_all",
    "replace_index",
]
