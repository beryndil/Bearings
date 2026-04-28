"""DB-layer integration tests for ``bearings.db.vault``.

Covers the cache CRUD round-trip + the upsert-by-path discipline that
keeps ``id`` stable across rescans (see ``bearings.db.vault`` module
docstring for the rationale).

References:

* ``docs/architecture-v1.md`` §1.1.3 — vault table.
* ``docs/behavior/vault.md`` §"Failure modes" — re-scan on every
  list request; vanished paths drop from the cache.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest

from bearings.config.constants import VAULT_KIND_PLAN, VAULT_KIND_TODO
from bearings.db import get_connection_factory, load_schema
from bearings.db.vault import (
    ScannedDoc,
    VaultEntry,
    get,
    get_by_path,
    list_all,
    replace_index,
)


@pytest.fixture
async def connection(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    factory = get_connection_factory(tmp_path / "vault.db")
    async with factory() as conn:
        await load_schema(conn)
        yield conn


def _doc(path: str, slug: str, *, kind: str = VAULT_KIND_PLAN, mtime: int = 1000) -> ScannedDoc:
    return ScannedDoc(
        path=path,
        slug=slug,
        title=f"Title {slug}",
        kind=kind,
        mtime=mtime,
        size=len(slug) * 10,
    )


async def test_replace_index_inserts_and_returns_rows(
    connection: aiosqlite.Connection,
) -> None:
    docs = [
        _doc("/abs/a.md", "a"),
        _doc("/abs/b.md", "b", kind=VAULT_KIND_TODO),
    ]
    rows = await replace_index(connection, docs)
    assert {r.path for r in rows} == {"/abs/a.md", "/abs/b.md"}
    assert all(r.id > 0 for r in rows)
    assert all(r.last_indexed_at > 0 for r in rows)


async def test_replace_index_preserves_id_on_upsert(
    connection: aiosqlite.Connection,
) -> None:
    """The same path across two rescans keeps the same ``id`` row."""
    docs_v1 = [_doc("/abs/foo.md", "foo", mtime=1000)]
    rows_v1 = await replace_index(connection, docs_v1)
    original_id = rows_v1[0].id

    # Rescan with updated mtime + size — id must persist.
    docs_v2 = [
        ScannedDoc(
            path="/abs/foo.md",
            slug="foo",
            title="Foo v2",
            kind=VAULT_KIND_PLAN,
            mtime=2000,
            size=999,
        )
    ]
    rows_v2 = await replace_index(connection, docs_v2)
    assert len(rows_v2) == 1
    assert rows_v2[0].id == original_id
    assert rows_v2[0].mtime == 2000
    assert rows_v2[0].title == "Foo v2"
    assert rows_v2[0].size == 999


async def test_replace_index_deletes_vanished_paths(
    connection: aiosqlite.Connection,
) -> None:
    docs_v1 = [
        _doc("/abs/keep.md", "keep"),
        _doc("/abs/gone.md", "gone"),
    ]
    await replace_index(connection, docs_v1)
    docs_v2 = [_doc("/abs/keep.md", "keep")]
    rows_v2 = await replace_index(connection, docs_v2)
    assert {r.path for r in rows_v2} == {"/abs/keep.md"}


async def test_replace_index_with_empty_scan_clears_cache(
    connection: aiosqlite.Connection,
) -> None:
    """An empty rescan represents a fully-unconfigured vault."""
    await replace_index(connection, [_doc("/abs/x.md", "x")])
    rows = await replace_index(connection, [])
    assert rows == []
    assert await list_all(connection) == []


async def test_list_all_orders_kind_then_mtime_desc(
    connection: aiosqlite.Connection,
) -> None:
    """plans before todos; within each, newer mtime first."""
    docs = [
        _doc("/abs/p1.md", "p1", kind=VAULT_KIND_PLAN, mtime=1000),
        _doc("/abs/p2.md", "p2", kind=VAULT_KIND_PLAN, mtime=2000),
        _doc("/abs/t1.md", "t1", kind=VAULT_KIND_TODO, mtime=1500),
        _doc("/abs/t2.md", "t2", kind=VAULT_KIND_TODO, mtime=500),
    ]
    await replace_index(connection, docs)
    rows = await list_all(connection)
    assert [r.slug for r in rows] == ["p2", "p1", "t1", "t2"]


async def test_list_all_kind_filter(connection: aiosqlite.Connection) -> None:
    docs = [
        _doc("/abs/p.md", "p", kind=VAULT_KIND_PLAN),
        _doc("/abs/t.md", "t", kind=VAULT_KIND_TODO),
    ]
    await replace_index(connection, docs)
    plans = await list_all(connection, kind=VAULT_KIND_PLAN)
    todos = await list_all(connection, kind=VAULT_KIND_TODO)
    assert [r.slug for r in plans] == ["p"]
    assert [r.slug for r in todos] == ["t"]


async def test_list_all_rejects_unknown_kind(
    connection: aiosqlite.Connection,
) -> None:
    with pytest.raises(ValueError, match="kind"):
        await list_all(connection, kind="snippet")


async def test_get_returns_row_then_none(connection: aiosqlite.Connection) -> None:
    rows = await replace_index(connection, [_doc("/abs/x.md", "x")])
    fetched = await get(connection, rows[0].id)
    assert isinstance(fetched, VaultEntry)
    assert fetched.path == "/abs/x.md"
    assert await get(connection, 99_999) is None


async def test_get_by_path_round_trips(connection: aiosqlite.Connection) -> None:
    await replace_index(connection, [_doc("/abs/y.md", "y")])
    fetched = await get_by_path(connection, "/abs/y.md")
    assert fetched is not None
    assert fetched.slug == "y"
    assert await get_by_path(connection, "/abs/missing.md") is None


async def test_replace_index_rejects_unknown_kind(
    connection: aiosqlite.Connection,
) -> None:
    bogus = ScannedDoc(
        path="/abs/x.md",
        slug="x",
        title=None,
        kind="snippet",
        mtime=1,
        size=2,
    )
    with pytest.raises(ValueError, match="kind"):
        await replace_index(connection, [bogus])
