"""Integration tests for ``bearings.db.templates`` + ``bearings.agent.templates``.

Round-trips Template CRUD against a fresh SQLite. The
``build_session_config_from_template`` bridge is superseded by
:mod:`bearings.agent.session_assembly`; those tests have been removed.

References:

* ``docs/architecture-v1.md`` §1.1.3 + §1.1.4 — db CRUD + agent
  bridge.
* ``docs/behavior/chat.md`` — new-session-from-template UX.
* ``docs/behavior/keyboard-shortcuts.md`` §"Create" — ``t`` chord.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest

from bearings.db import get_connection_factory, load_schema
from bearings.db.templates import (
    create,
    delete,
    get,
    get_by_name,
    list_all,
    update,
)


@pytest.fixture
async def connection(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    factory = get_connection_factory(tmp_path / "templates.db")
    async with factory() as conn:
        await load_schema(conn)
        yield conn


async def test_create_round_trips(connection: aiosqlite.Connection) -> None:
    template = await create(
        connection,
        name="Workhorse",
        model="sonnet",
        description="Sonnet + Opus advisor",
        advisor_model="opus",
        advisor_max_uses=5,
        effort_level="auto",
        permission_profile="standard",
        tag_names=("bearings/exec",),
    )
    assert template.id > 0
    fetched = await get(connection, template.id)
    assert fetched is not None
    assert fetched == template
    assert fetched.tag_names == ("bearings/exec",)


async def test_get_returns_none_for_unknown_id(connection: aiosqlite.Connection) -> None:
    assert await get(connection, 9999) is None


async def test_get_by_name_finds_template(connection: aiosqlite.Connection) -> None:
    created = await create(connection, name="Named", model="haiku")
    fetched = await get_by_name(connection, "Named")
    assert fetched is not None
    assert fetched.id == created.id
    assert await get_by_name(connection, "absent") is None


async def test_unique_name_constraint_rejects_duplicate(
    connection: aiosqlite.Connection,
) -> None:
    await create(connection, name="Dupe", model="sonnet")
    with pytest.raises(aiosqlite.IntegrityError):
        await create(connection, name="Dupe", model="haiku")


async def test_list_all_orders_alphabetically(connection: aiosqlite.Connection) -> None:
    await create(connection, name="Charlie", model="sonnet")
    await create(connection, name="Alpha", model="sonnet")
    await create(connection, name="Beta", model="sonnet")
    rows = await list_all(connection)
    assert [t.name for t in rows] == ["Alpha", "Beta", "Charlie"]


async def test_update_preserves_created_at_and_bumps_updated_at(
    connection: aiosqlite.Connection,
) -> None:
    original = await create(connection, name="Mutable", model="sonnet")
    updated = await update(
        connection,
        original.id,
        name="Mutable",
        description="now with description",
        model="haiku",
        advisor_model="opus",
        advisor_max_uses=3,
        effort_level="low",
        permission_profile="restricted",
        system_prompt_baseline=None,
        working_dir_default=None,
        tag_names=("renamed",),
    )
    assert updated is not None
    assert updated.created_at == original.created_at
    assert updated.model == "haiku"
    assert updated.tag_names == ("renamed",)


async def test_update_returns_none_for_unknown_id(
    connection: aiosqlite.Connection,
) -> None:
    result = await update(
        connection,
        9999,
        name="ghost",
        model="sonnet",
        description=None,
        advisor_model=None,
        advisor_max_uses=0,
        effort_level="auto",
        permission_profile="standard",
        system_prompt_baseline=None,
        working_dir_default=None,
        tag_names=(),
    )
    assert result is None


async def test_delete_returns_true_on_existing_row(
    connection: aiosqlite.Connection,
) -> None:
    template = await create(connection, name="ToDelete", model="sonnet")
    assert await delete(connection, template.id) is True
    assert await get(connection, template.id) is None
    assert await delete(connection, template.id) is False
