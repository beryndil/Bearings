"""Integration tests for ``bearings.db.memories`` against a real SQLite.

Round-trips the CRUD surface plus exercises FK cascade
(``ON DELETE CASCADE`` on ``tag_memories.tag_id``) so deleting a
parent tag sweeps its memories.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest

from bearings.db import get_connection_factory, load_schema
from bearings.db import tags as tags_db
from bearings.db.memories import (
    create,
    delete,
    get,
    list_for_tag,
    update,
)


@pytest.fixture
async def connection(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    factory = get_connection_factory(tmp_path / "memories.db")
    async with factory() as conn:
        await load_schema(conn)
        yield conn


async def test_create_round_trips(connection: aiosqlite.Connection) -> None:
    parent = await tags_db.create(connection, name="t1")
    m = await create(
        connection,
        tag_id=parent.id,
        title="anchor",
        body="cite arch",
        enabled=True,
    )
    fetched = await get(connection, m.id)
    assert fetched == m


async def test_get_returns_none_for_unknown(connection: aiosqlite.Connection) -> None:
    assert await get(connection, 99_999) is None


async def test_create_rejects_unknown_tag_fk(
    connection: aiosqlite.Connection,
) -> None:
    with pytest.raises(aiosqlite.IntegrityError):
        await create(connection, tag_id=999, title="t", body="b")


async def test_list_for_tag_returns_insertion_order(
    connection: aiosqlite.Connection,
) -> None:
    parent = await tags_db.create(connection, name="t-list")
    a = await create(connection, tag_id=parent.id, title="a", body="aa")
    b = await create(connection, tag_id=parent.id, title="b", body="bb")
    c = await create(connection, tag_id=parent.id, title="c", body="cc")
    rows = await list_for_tag(connection, parent.id)
    assert [m.id for m in rows] == [a.id, b.id, c.id]


async def test_list_for_tag_only_enabled_filters_disabled(
    connection: aiosqlite.Connection,
) -> None:
    parent = await tags_db.create(connection, name="t-filter")
    on1 = await create(connection, tag_id=parent.id, title="on1", body="b", enabled=True)
    await create(connection, tag_id=parent.id, title="off", body="b", enabled=False)
    on2 = await create(connection, tag_id=parent.id, title="on2", body="b", enabled=True)
    rows = await list_for_tag(connection, parent.id, only_enabled=True)
    assert [m.id for m in rows] == [on1.id, on2.id]
    # Without the filter, all three appear.
    full = await list_for_tag(connection, parent.id, only_enabled=False)
    assert len(full) == 3


async def test_update_replaces_mutable_fields(
    connection: aiosqlite.Connection,
) -> None:
    parent = await tags_db.create(connection, name="t-upd")
    m = await create(connection, tag_id=parent.id, title="orig", body="orig-body")
    updated = await update(connection, m.id, title="renamed", body="new-body", enabled=False)
    assert updated is not None
    assert updated.title == "renamed"
    assert updated.body == "new-body"
    assert updated.enabled is False
    assert updated.tag_id == parent.id  # tag_id preserved
    assert updated.created_at == m.created_at  # created_at preserved


async def test_update_returns_none_on_unknown(
    connection: aiosqlite.Connection,
) -> None:
    result = await update(connection, 99_999, title="x", body="y", enabled=True)
    assert result is None


async def test_delete_returns_true_on_existing_row(
    connection: aiosqlite.Connection,
) -> None:
    parent = await tags_db.create(connection, name="t-del")
    m = await create(connection, tag_id=parent.id, title="rm", body="rm")
    assert await delete(connection, m.id) is True
    assert await get(connection, m.id) is None
    assert await delete(connection, m.id) is False


async def test_tag_delete_cascades_to_memories(
    connection: aiosqlite.Connection,
) -> None:
    parent = await tags_db.create(connection, name="t-cascade")
    m = await create(connection, tag_id=parent.id, title="bye", body="bye")
    await tags_db.delete(connection, parent.id)
    assert await get(connection, m.id) is None
