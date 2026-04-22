"""Checklist store unit tests (Slice 1 of nimble-checking-heron).

Covers migration shape, the `sessions.kind` discriminator, CRUD on
`checklists` / `checklist_items`, and cascade-on-delete from session
removal. The API layer + guards land in Slice 2 and have their own
tests — this file exercises `db/_checklists.py` directly."""

from __future__ import annotations

from pathlib import Path

import pytest

from bearings.db.store import (
    create_checklist,
    create_item,
    create_session,
    delete_item,
    delete_session,
    get_checklist,
    get_item,
    get_session,
    init_db,
    reorder_items,
    toggle_item,
    update_checklist,
    update_item,
)

# --- migration shape -------------------------------------------------


@pytest.mark.asyncio
async def test_migration_creates_checklist_tables(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cursor:
            tables = [row[0] async for row in cursor]
        assert "checklists" in tables
        assert "checklist_items" in tables
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name IN ('idx_checklist_items_checklist', 'idx_checklist_items_parent')"
        ) as cursor:
            idx = {row[0] async for row in cursor}
        assert idx == {"idx_checklist_items_checklist", "idx_checklist_items_parent"}
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_existing_sessions_backfill_as_chat(tmp_path: Path) -> None:
    """The `kind` column is NOT NULL DEFAULT 'chat' — every session
    row created via the existing `create_session` path should land as
    a chat without the caller having to opt in."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        row = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6")
        assert row["kind"] == "chat"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_create_session_accepts_checklist_kind(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        row = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        assert row["kind"] == "checklist"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_create_session_rejects_unknown_kind(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        with pytest.raises(ValueError):
            await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="bogus")
    finally:
        await conn.close()


# --- checklists ------------------------------------------------------


@pytest.mark.asyncio
async def test_create_checklist_round_trips(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        row = await create_checklist(conn, session["id"], notes="pre-flight")
        assert row["session_id"] == session["id"]
        assert row["notes"] == "pre-flight"
        assert row["items"] == []
        assert row["created_at"]
        assert row["updated_at"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_update_checklist_notes(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        await create_checklist(conn, session["id"])
        row = await update_checklist(conn, session["id"], fields={"notes": "after"})
        assert row is not None
        assert row["notes"] == "after"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_update_checklist_ignores_unknown_fields(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        await create_checklist(conn, session["id"], notes="original")
        row = await update_checklist(conn, session["id"], fields={"bogus": "value"})
        assert row is not None
        assert row["notes"] == "original"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_update_missing_checklist_returns_none(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        row = await update_checklist(conn, "nonexistent", fields={"notes": "x"})
        assert row is None
    finally:
        await conn.close()


# --- items -----------------------------------------------------------


@pytest.mark.asyncio
async def test_create_item_appends_by_default(tmp_path: Path) -> None:
    """Omitting sort_order appends — `MAX(sort_order) + 1` among
    siblings. Four items in order should carry sort_order 0..3."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        await create_checklist(conn, session["id"])
        labels = ["a", "b", "c", "d"]
        items = [await create_item(conn, session["id"], label=lbl) for lbl in labels]
        assert [i["sort_order"] for i in items if i is not None] == [0, 1, 2, 3]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_create_item_returns_none_for_missing_checklist(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        row = await create_item(conn, "nonexistent", label="x")
        assert row is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_toggle_item_round_trip(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        await create_checklist(conn, session["id"])
        item = await create_item(conn, session["id"], label="first")
        assert item is not None
        checked = await toggle_item(conn, item["id"], checked=True)
        assert checked is not None
        assert checked["checked_at"] is not None
        unchecked = await toggle_item(conn, item["id"], checked=False)
        assert unchecked is not None
        assert unchecked["checked_at"] is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_update_item_fields(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        await create_checklist(conn, session["id"])
        item = await create_item(conn, session["id"], label="old")
        assert item is not None
        updated = await update_item(conn, item["id"], fields={"label": "new", "notes": "why"})
        assert updated is not None
        assert updated["label"] == "new"
        assert updated["notes"] == "why"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_delete_item_removes_row(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        await create_checklist(conn, session["id"])
        item = await create_item(conn, session["id"], label="doomed")
        assert item is not None
        assert await delete_item(conn, item["id"]) is True
        assert await get_item(conn, item["id"]) is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_delete_missing_item_returns_false(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        assert await delete_item(conn, 9999) is False
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_reorder_items_rewrites_sort_order(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        await create_checklist(conn, session["id"])
        a = await create_item(conn, session["id"], label="a")
        b = await create_item(conn, session["id"], label="b")
        c = await create_item(conn, session["id"], label="c")
        assert a and b and c
        # Reverse the order.
        written = await reorder_items(conn, session["id"], [c["id"], b["id"], a["id"]])
        assert written == 3
        checklist = await get_checklist(conn, session["id"])
        assert checklist is not None
        labels_in_order = [i["label"] for i in checklist["items"]]
        assert labels_in_order == ["c", "b", "a"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_reorder_ignores_foreign_ids(tmp_path: Path) -> None:
    """Reordering with an id belonging to a different checklist must
    silently skip that id — a client can't reorder a list it doesn't
    own even if it guesses the id."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        s1 = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        s2 = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        await create_checklist(conn, s1["id"])
        await create_checklist(conn, s2["id"])
        a = await create_item(conn, s1["id"], label="a")
        foreign = await create_item(conn, s2["id"], label="foreign")
        assert a and foreign
        # Try to reorder s1 using a foreign id mixed in.
        written = await reorder_items(conn, s1["id"], [foreign["id"], a["id"]])
        # Only the own-checklist row should be rewritten.
        assert written == 1
    finally:
        await conn.close()


# --- cascade ---------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_session_cascades_to_checklist(tmp_path: Path) -> None:
    """Deleting the session row should sweep the checklist and its
    items via `ON DELETE CASCADE`. Guards against orphan rows."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        await create_checklist(conn, session["id"])
        item = await create_item(conn, session["id"], label="to-cascade")
        assert item is not None
        await delete_session(conn, session["id"])
        assert await get_session(conn, session["id"]) is None
        assert await get_checklist(conn, session["id"]) is None
        assert await get_item(conn, item["id"]) is None
    finally:
        await conn.close()
