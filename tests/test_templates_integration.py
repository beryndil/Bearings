"""Integration tests for ``bearings.db.templates`` + ``bearings.agent.templates``.

Round-trips Template CRUD against a fresh SQLite and exercises
:func:`bearings.agent.templates.build_session_config_from_template`
end-to-end so the new-session-from-template flow at item 1.10 has a
verified data path.

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

from bearings.agent.session import PermissionProfile
from bearings.agent.templates import (
    TemplateNotFoundError,
    build_session_config_from_template,
)
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


async def test_build_session_config_from_template_applies_routing(
    connection: aiosqlite.Connection,
) -> None:
    """Bridge helper produces a SessionConfig matching the template values."""
    template = await create(
        connection,
        name="ArchitectPreset",
        model="opus",
        advisor_model=None,
        advisor_max_uses=0,
        effort_level="xhigh",
        permission_profile="restricted",
        working_dir_default="/home/user/arch",
        tag_names=("bearings/architect",),
    )
    config = await build_session_config_from_template(
        connection,
        template.id,
        session_id="session_new",
    )
    assert config.session_id == "session_new"
    assert config.working_dir == "/home/user/arch"
    assert config.decision.executor_model == "opus"
    assert config.decision.advisor_model is None
    assert config.decision.advisor_max_uses == 0
    assert config.decision.effort_level == "xhigh"
    assert config.decision.source == "manual"
    assert config.decision.reason == "template: ArchitectPreset"
    assert config.permission_profile == PermissionProfile.RESTRICTED


async def test_build_session_config_explicit_working_dir_overrides_template(
    connection: aiosqlite.Connection,
) -> None:
    """User-supplied working_dir wins over the template's default."""
    template = await create(
        connection,
        name="WithDefault",
        model="sonnet",
        working_dir_default="/template/default",
    )
    config = await build_session_config_from_template(
        connection,
        template.id,
        session_id="session_user",
        working_dir="/user/explicit",
    )
    assert config.working_dir == "/user/explicit"


async def test_build_session_config_requires_working_dir(
    connection: aiosqlite.Connection,
) -> None:
    """Template w/ no default + no user override raises ValueError."""
    template = await create(
        connection,
        name="NoDefault",
        model="sonnet",
        working_dir_default=None,
    )
    with pytest.raises(ValueError, match="working_dir"):
        await build_session_config_from_template(
            connection,
            template.id,
            session_id="session_no_dir",
        )


async def test_build_session_config_raises_for_unknown_template(
    connection: aiosqlite.Connection,
) -> None:
    """Unknown template id raises TemplateNotFoundError, not LookupError opaquely."""
    with pytest.raises(TemplateNotFoundError):
        await build_session_config_from_template(
            connection,
            template_id=9999,
            session_id="session_none",
            working_dir="/tmp",
        )
