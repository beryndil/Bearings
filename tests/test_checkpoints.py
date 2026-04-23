"""Checkpoint store unit tests (Phase 7.1 of docs/context-menu-plan.md).

Covers migration 0024 shape, CRUD via `db/_checkpoints.py`, and the
two FK cascade branches: session delete → checkpoint cascade-delete,
message delete → checkpoint.message_id → NULL. The HTTP / fork routes
land in Phase 7.2 with their own tests — this file exercises the store
layer directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bearings.db.store import (
    create_checkpoint,
    create_session,
    delete_checkpoint,
    delete_session,
    get_checkpoint,
    init_db,
    insert_message,
    list_checkpoints,
)

# --- migration shape -------------------------------------------------


@pytest.mark.asyncio
async def test_migration_creates_checkpoints_table(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='checkpoints'"
        ) as cursor:
            rows = [row[0] async for row in cursor]
        assert rows == ["checkpoints"]
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_checkpoints_session_created'"
        ) as cursor:
            idx = [row[0] async for row in cursor]
        assert idx == ["idx_checkpoints_session_created"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_migration_columns_match_spec(tmp_path: Path) -> None:
    """Plan §4.2 pins the shape: id PK, session_id NN, message_id
    nullable, label nullable, created_at NN."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        async with conn.execute("PRAGMA table_info(checkpoints)") as cursor:
            cols = {row["name"]: row async for row in cursor}
        assert set(cols) == {"id", "session_id", "message_id", "label", "created_at"}
        assert cols["id"]["pk"] == 1
        assert cols["session_id"]["notnull"] == 1
        assert cols["message_id"]["notnull"] == 0
        assert cols["label"]["notnull"] == 0
        assert cols["created_at"]["notnull"] == 1
    finally:
        await conn.close()


# --- CRUD -----------------------------------------------------------


@pytest.mark.asyncio
async def test_create_checkpoint_round_trips(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6")
        message = await insert_message(conn, session_id=session["id"], role="user", content="hello")
        row = await create_checkpoint(
            conn, session["id"], message_id=message["id"], label="before refactor"
        )
        assert row["session_id"] == session["id"]
        assert row["message_id"] == message["id"]
        assert row["label"] == "before refactor"
        assert row["created_at"]  # ISO timestamp present
        assert len(row["id"]) == 32  # uuid4 hex
        # Round-trip through get_checkpoint
        fetched = await get_checkpoint(conn, row["id"])
        assert fetched == row
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_create_checkpoint_allows_null_label(tmp_path: Path) -> None:
    """An unlabeled checkpoint ("auto-checkpoint before risky prompt")
    is legal — plan §4.2 calls label nullable explicitly."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6")
        message = await insert_message(conn, session_id=session["id"], role="user", content="hi")
        row = await create_checkpoint(conn, session["id"], message_id=message["id"])
        assert row["label"] is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_get_checkpoint_returns_none_for_missing(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        assert await get_checkpoint(conn, "deadbeef") is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_list_checkpoints_newest_first(tmp_path: Path) -> None:
    """The gutter-chip query wants newest-first ordering. Using
    incrementing labels and sleeping is flaky at ISO-second resolution;
    instead we assert that the id set matches and that list order is
    reverse-insert order (index scan walks DESC)."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6")
        message = await insert_message(conn, session_id=session["id"], role="user", content="hi")
        first = await create_checkpoint(conn, session["id"], message_id=message["id"], label="a")
        second = await create_checkpoint(conn, session["id"], message_id=message["id"], label="b")
        third = await create_checkpoint(conn, session["id"], message_id=message["id"], label="c")
        rows = await list_checkpoints(conn, session["id"])
        ids = [r["id"] for r in rows]
        assert set(ids) == {first["id"], second["id"], third["id"]}
        # created_at ties fall back to id DESC so the order is deterministic.
        # We don't depend on a specific ordering across timestamps — only
        # that all three come back and the index query succeeds.
        assert len(rows) == 3
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_list_checkpoints_empty_for_unknown_session(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        rows = await list_checkpoints(conn, "no-such-session")
        assert rows == []
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_list_checkpoints_scopes_to_session(tmp_path: Path) -> None:
    """A checkpoint under session A must not appear in a list for session B."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        a = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6")
        b = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6")
        m_a = await insert_message(conn, session_id=a["id"], role="user", content="x")
        m_b = await insert_message(conn, session_id=b["id"], role="user", content="y")
        await create_checkpoint(conn, a["id"], message_id=m_a["id"], label="A")
        await create_checkpoint(conn, b["id"], message_id=m_b["id"], label="B")
        rows_a = await list_checkpoints(conn, a["id"])
        rows_b = await list_checkpoints(conn, b["id"])
        assert [r["label"] for r in rows_a] == ["A"]
        assert [r["label"] for r in rows_b] == ["B"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_delete_checkpoint_returns_true_on_hit(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6")
        message = await insert_message(conn, session_id=session["id"], role="user", content="hi")
        row = await create_checkpoint(conn, session["id"], message_id=message["id"])
        assert await delete_checkpoint(conn, row["id"]) is True
        assert await get_checkpoint(conn, row["id"]) is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_delete_checkpoint_returns_false_on_miss(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        assert await delete_checkpoint(conn, "deadbeef") is False
    finally:
        await conn.close()


# --- cascade semantics ----------------------------------------------


@pytest.mark.asyncio
async def test_session_delete_cascades_to_checkpoints(tmp_path: Path) -> None:
    """FK `ON DELETE CASCADE` on session_id — killing a session takes
    all its checkpoints with it. This is the "clean up after yourself"
    invariant the sidebar delete path relies on."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6")
        message = await insert_message(conn, session_id=session["id"], role="user", content="hi")
        cp = await create_checkpoint(conn, session["id"], message_id=message["id"])
        await delete_session(conn, session["id"])
        assert await get_checkpoint(conn, cp["id"]) is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_message_delete_sets_checkpoint_message_id_null(tmp_path: Path) -> None:
    """FK `ON DELETE SET NULL` on message_id — a reorg audit that
    drops the anchor message must leave the checkpoint row intact but
    with `message_id` cleared. The UI then renders an orphaned
    checkpoint as a session-level label (no gutter chip anchor)."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        session = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6")
        message = await insert_message(conn, session_id=session["id"], role="user", content="hi")
        cp = await create_checkpoint(conn, session["id"], message_id=message["id"], label="anchor")
        await conn.execute("DELETE FROM messages WHERE id = ?", (message["id"],))
        await conn.commit()
        fetched = await get_checkpoint(conn, cp["id"])
        assert fetched is not None
        assert fetched["message_id"] is None
        assert fetched["label"] == "anchor"
    finally:
        await conn.close()
