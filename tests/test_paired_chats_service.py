"""Tests for :mod:`bearings.agent.paired_chats` spawn-and-link service."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from bearings.agent.paired_chats import (
    PairedChatSpawnError,
    detach_paired_chat,
    spawn_paired_chat,
)
from bearings.config.constants import (
    PAIRED_CHAT_SPAWNED_BY_DRIVER,
    SESSION_KIND_CHECKLIST,
)
from bearings.db import checklists as checklists_db
from bearings.db import sessions as sessions_db
from bearings.db import tags as tags_db
from bearings.db.connection import load_schema


@pytest.fixture
async def conn(tmp_path: Path):
    db_path = tmp_path / "pc.db"
    async with aiosqlite.connect(db_path) as connection:
        await load_schema(connection)
        yield connection


async def _new_checklist_with_item(
    conn: aiosqlite.Connection, *, model: str = "sonnet", working_dir: str = "/parent/wd"
) -> tuple[str, int]:
    """Make a fresh checklist + leaf item; return (checklist_id, item_id)."""
    checklist = await sessions_db.create(
        conn,
        kind=SESSION_KIND_CHECKLIST,
        title="cl",
        working_dir=working_dir,
        model=model,
    )
    item = await checklists_db.create(conn, checklist_id=checklist.id, label="leaf")
    return checklist.id, item.id


async def test_spawn_creates_chat_session_and_records_leg(
    conn: aiosqlite.Connection,
) -> None:
    _checklist_id, item_id = await _new_checklist_with_item(conn)
    chat_id, config = await spawn_paired_chat(conn, item_id=item_id)
    assert chat_id.startswith("ses_")
    chat = await sessions_db.get(conn, chat_id)
    assert chat is not None and chat.kind == "chat"
    assert chat.title == "leaf"
    assert chat.checklist_item_id == item_id
    item_now = await checklists_db.get(conn, item_id)
    assert item_now is not None and item_now.chat_session_id == chat_id
    legs = await checklists_db.list_legs(conn, item_id)
    assert len(legs) == 1 and legs[0].spawned_by == "user"
    # Returned config carries the same id + working_dir.
    assert config.session_id == chat_id
    assert config.working_dir == "/parent/wd"


async def test_spawn_inherits_parent_tags(conn: aiosqlite.Connection) -> None:
    checklist_id, item_id = await _new_checklist_with_item(conn)
    tag_a = await tags_db.create(conn, name="alpha")
    tag_b = await tags_db.create(conn, name="beta")
    await tags_db.attach(conn, session_id=checklist_id, tag_id=tag_a.id)
    await tags_db.attach(conn, session_id=checklist_id, tag_id=tag_b.id)
    chat_id, _config = await spawn_paired_chat(conn, item_id=item_id)
    chat_tag_ids = {tag.id for tag in await tags_db.list_for_session(conn, chat_id)}
    assert chat_tag_ids == {tag_a.id, tag_b.id}


async def test_spawn_idempotent_for_open_existing_pair(
    conn: aiosqlite.Connection,
) -> None:
    _cid, item_id = await _new_checklist_with_item(conn)
    first_id, _ = await spawn_paired_chat(conn, item_id=item_id)
    second_id, _ = await spawn_paired_chat(conn, item_id=item_id)
    assert first_id == second_id
    legs = await checklists_db.list_legs(conn, item_id)
    # Idempotent — only one leg recorded.
    assert len(legs) == 1


async def test_spawn_after_closed_pair_creates_fresh_session(
    conn: aiosqlite.Connection,
) -> None:
    _cid, item_id = await _new_checklist_with_item(conn)
    first_id, _ = await spawn_paired_chat(conn, item_id=item_id)
    await sessions_db.close(conn, first_id)
    # Behavior: doc says when chat is closed, the leaf shows "Reopen
    # chat" and the pair pointer is preserved — the spawn is *not*
    # idempotent against a closed chat (a fresh click would not
    # navigate to a closed session). The implementation chooses to
    # spawn a new pair in this case.
    second_id, _ = await spawn_paired_chat(conn, item_id=item_id)
    assert first_id != second_id


async def test_spawn_rejects_parent_item(conn: aiosqlite.Connection) -> None:
    checklist_id, parent_id = await _new_checklist_with_item(conn)
    # Attach a child so parent_id is no longer a leaf.
    await checklists_db.create(
        conn, checklist_id=checklist_id, parent_item_id=parent_id, label="child"
    )
    with pytest.raises(PairedChatSpawnError, match="parent"):
        await spawn_paired_chat(conn, item_id=parent_id)


async def test_spawn_rejects_unknown_item(conn: aiosqlite.Connection) -> None:
    with pytest.raises(PairedChatSpawnError, match="not found"):
        await spawn_paired_chat(conn, item_id=9999)


async def test_spawn_with_driver_records_correctly(conn: aiosqlite.Connection) -> None:
    _cid, item_id = await _new_checklist_with_item(conn)
    chat_id, _config = await spawn_paired_chat(
        conn,
        item_id=item_id,
        spawned_by=PAIRED_CHAT_SPAWNED_BY_DRIVER,
        plug="leg-2 plug body",
    )
    legs = await checklists_db.list_legs(conn, item_id)
    assert legs[0].spawned_by == "driver"
    chat = await sessions_db.get(conn, chat_id)
    assert chat is not None and chat.description == "leg-2 plug body"


async def test_spawn_rejects_unknown_spawned_by(conn: aiosqlite.Connection) -> None:
    _cid, item_id = await _new_checklist_with_item(conn)
    with pytest.raises(PairedChatSpawnError, match="spawned_by"):
        await spawn_paired_chat(conn, item_id=item_id, spawned_by="bogus")


async def test_detach_clears_pair_pointer(conn: aiosqlite.Connection) -> None:
    _cid, item_id = await _new_checklist_with_item(conn)
    await spawn_paired_chat(conn, item_id=item_id)
    detached = await detach_paired_chat(conn, item_id)
    assert detached is not None and detached.chat_session_id is None


async def test_title_override_used(conn: aiosqlite.Connection) -> None:
    _cid, item_id = await _new_checklist_with_item(conn)
    chat_id, _ = await spawn_paired_chat(conn, item_id=item_id, title_override="Custom Title")
    chat = await sessions_db.get(conn, chat_id)
    assert chat is not None and chat.title == "Custom Title"
