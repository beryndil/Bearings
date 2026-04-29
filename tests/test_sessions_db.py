"""Tests for ``bearings.db.sessions`` (item 1.7 — sessions CRUD).

Covers the surface item 1.7 needs: row create, get, exists, kind /
closed introspection, close / reopen lifecycle, delete cascade.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from bearings.config.constants import (
    SESSION_KIND_CHAT,
    SESSION_KIND_CHECKLIST,
)
from bearings.db import sessions as sessions_db
from bearings.db.connection import load_schema


@pytest.fixture
async def conn(tmp_path: Path):
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(db_path) as connection:
        await load_schema(connection)
        yield connection


async def test_create_chat_session_returns_validated_row(conn: aiosqlite.Connection) -> None:
    session = await sessions_db.create(
        conn,
        kind=SESSION_KIND_CHAT,
        title="Hello",
        working_dir="/tmp/wd",
        model="sonnet",
    )
    assert session.id.startswith("ses_")
    assert session.kind == SESSION_KIND_CHAT
    assert session.title == "Hello"
    assert session.working_dir == "/tmp/wd"
    assert session.model == "sonnet"
    assert session.closed_at is None
    assert session.message_count == 0


async def test_get_returns_none_for_missing(conn: aiosqlite.Connection) -> None:
    assert await sessions_db.get(conn, "ses_nonexistent") is None


async def test_exists_true_after_create(conn: aiosqlite.Connection) -> None:
    session = await sessions_db.create(
        conn, kind=SESSION_KIND_CHECKLIST, title="C", working_dir="/wd", model="haiku"
    )
    assert await sessions_db.exists(conn, session.id)


async def test_get_kind_distinguishes_chat_from_checklist(conn: aiosqlite.Connection) -> None:
    chat = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title="t", working_dir="/wd", model="sonnet"
    )
    checklist = await sessions_db.create(
        conn, kind=SESSION_KIND_CHECKLIST, title="c", working_dir="/wd", model="sonnet"
    )
    assert await sessions_db.get_kind(conn, chat.id) == "chat"
    assert await sessions_db.get_kind(conn, checklist.id) == "checklist"
    assert await sessions_db.get_kind(conn, "ses_missing") is None


async def test_is_closed_tristate(conn: aiosqlite.Connection) -> None:
    session = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title="t", working_dir="/wd", model="sonnet"
    )
    assert await sessions_db.is_closed(conn, session.id) is False
    await sessions_db.close(conn, session.id)
    assert await sessions_db.is_closed(conn, session.id) is True
    assert await sessions_db.is_closed(conn, "ses_missing") is None


async def test_close_then_reopen_round_trip(conn: aiosqlite.Connection) -> None:
    session = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title="t", working_dir="/wd", model="sonnet"
    )
    closed = await sessions_db.close(conn, session.id)
    assert closed is not None and closed.closed_at is not None
    reopened = await sessions_db.reopen(conn, session.id)
    assert reopened is not None and reopened.closed_at is None


async def test_update_title(conn: aiosqlite.Connection) -> None:
    session = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title="old", working_dir="/wd", model="sonnet"
    )
    updated = await sessions_db.update_title(conn, session.id, title="new")
    assert updated is not None and updated.title == "new"


async def test_update_title_rejects_empty(conn: aiosqlite.Connection) -> None:
    session = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title="t", working_dir="/wd", model="sonnet"
    )
    with pytest.raises(ValueError):
        await sessions_db.update_title(conn, session.id, title="")


async def test_delete_returns_false_when_missing(conn: aiosqlite.Connection) -> None:
    assert (await sessions_db.delete(conn, "ses_missing")) is False


async def test_create_validates_kind(conn: aiosqlite.Connection) -> None:
    with pytest.raises(ValueError, match="kind"):
        await sessions_db.create(conn, kind="bogus", title="t", working_dir="/wd", model="sonnet")


async def test_create_validates_model(conn: aiosqlite.Connection) -> None:
    with pytest.raises(ValueError, match="model"):
        await sessions_db.create(
            conn, kind=SESSION_KIND_CHAT, title="t", working_dir="/wd", model="sonet"
        )


async def test_list_all_filters(conn: aiosqlite.Connection) -> None:
    a = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title="a", working_dir="/wd", model="sonnet"
    )
    b = await sessions_db.create(
        conn, kind=SESSION_KIND_CHECKLIST, title="b", working_dir="/wd", model="sonnet"
    )
    await sessions_db.close(conn, a.id)
    chats_open = await sessions_db.list_all(conn, kind="chat", include_closed=False)
    assert chats_open == []
    chats_all = await sessions_db.list_all(conn, kind="chat")
    assert {row.id for row in chats_all} == {a.id}
    every = await sessions_db.list_all(conn)
    assert {row.id for row in every} == {a.id, b.id}
