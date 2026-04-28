"""Integration tests for ``bearings.db.checkpoints`` against a real SQLite.

Round-trips :func:`create` / :func:`get` / :func:`list_for_session` /
:func:`count_for_session` / :func:`delete` against a freshly-bootstrapped
DB. Exercises the FK cascade behavior the schema declares
(``ON DELETE CASCADE`` on both ``session_id`` and ``message_id``) so a
session deletion sweeps its checkpoints.

References:

* ``docs/architecture-v1.md`` §1.1.3 — concern-module CRUD pattern.
* ``schema.sql`` — ``checkpoints`` table FK declarations.
* ``docs/behavior/context-menus.md`` §"Checkpoint" — list / delete /
  fork-from semantics.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest

from bearings.db import get_connection_factory, load_schema
from bearings.db.checkpoints import (
    count_for_session,
    create,
    delete,
    get,
    list_for_session,
)


@pytest.fixture
async def connection(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    """Open + bootstrap a fresh DB connection per test."""
    factory = get_connection_factory(tmp_path / "checkpoints.db")
    async with factory() as conn:
        await load_schema(conn)
        yield conn


async def _seed_session_with_message(
    connection: aiosqlite.Connection,
    *,
    session_id: str = "session_alpha",
    message_id: str = "msg_alpha_1",
) -> tuple[str, str]:
    """Insert one minimal session + one assistant message; return their ids."""
    timestamp = "2026-04-28T12:00:00+00:00"
    await connection.execute(
        "INSERT INTO sessions (id, kind, title, working_dir, model, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, "chat", "Alpha", "/tmp/alpha", "sonnet", timestamp, timestamp),
    )
    await connection.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (message_id, session_id, "assistant", "hello", timestamp),
    )
    await connection.commit()
    return session_id, message_id


async def test_create_round_trips_via_get(connection: aiosqlite.Connection) -> None:
    """create() inserts a row that get() returns verbatim."""
    session_id, message_id = await _seed_session_with_message(connection)
    cp = await create(
        connection,
        session_id=session_id,
        message_id=message_id,
        label="First checkpoint",
    )
    fetched = await get(connection, cp.id)
    assert fetched == cp


async def test_get_returns_none_for_unknown_id(connection: aiosqlite.Connection) -> None:
    """get() on an absent id returns None, not raises."""
    assert await get(connection, "cpt_does_not_exist") is None


async def test_list_for_session_returns_newest_first(
    connection: aiosqlite.Connection,
) -> None:
    """list_for_session() orders by created_at DESC (newest first)."""
    session_id, message_id = await _seed_session_with_message(connection)
    first = await create(connection, session_id=session_id, message_id=message_id, label="first")
    second = await create(connection, session_id=session_id, message_id=message_id, label="second")
    third = await create(connection, session_id=session_id, message_id=message_id, label="third")
    ordered = await list_for_session(connection, session_id)
    # The fixture's now_iso() resolution is per-second so all three may
    # share a created_at; the secondary id-DESC tiebreak keeps the order
    # deterministic. All three checkpoints must appear; the most recent
    # 'third' must come first under the (created_at DESC, id DESC) sort.
    assert {cp.label for cp in ordered} == {"first", "second", "third"}
    assert ordered[0].label == "third"
    assert {cp.id for cp in ordered} == {first.id, second.id, third.id}


async def test_list_for_session_returns_empty_for_unknown_session(
    connection: aiosqlite.Connection,
) -> None:
    """list_for_session() returns [] for a session with no checkpoints."""
    assert await list_for_session(connection, "session_nonexistent") == []


async def test_count_for_session_tracks_inserts(
    connection: aiosqlite.Connection,
) -> None:
    """count_for_session() reflects the running total."""
    session_id, message_id = await _seed_session_with_message(connection)
    assert await count_for_session(connection, session_id) == 0
    await create(connection, session_id=session_id, message_id=message_id, label="a")
    await create(connection, session_id=session_id, message_id=message_id, label="b")
    assert await count_for_session(connection, session_id) == 2


async def test_delete_returns_true_on_existing_row(
    connection: aiosqlite.Connection,
) -> None:
    """delete() returns True when a row was removed; False when nothing matched."""
    session_id, message_id = await _seed_session_with_message(connection)
    cp = await create(connection, session_id=session_id, message_id=message_id, label="rm")
    assert await delete(connection, cp.id) is True
    assert await get(connection, cp.id) is None
    # Second delete (idempotency check) returns False.
    assert await delete(connection, cp.id) is False


async def test_session_delete_cascades_to_checkpoints(
    connection: aiosqlite.Connection,
) -> None:
    """ON DELETE CASCADE on session_id removes orphaned checkpoints."""
    session_id, message_id = await _seed_session_with_message(connection)
    cp = await create(connection, session_id=session_id, message_id=message_id, label="bye")
    await connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    await connection.commit()
    assert await get(connection, cp.id) is None


async def test_checkpoint_create_after_session_then_replay(
    connection: aiosqlite.Connection,
) -> None:
    """Mid-conversation create + post-create messages: state matches creation moment.

    Behavior-doc-alignment test: per ``docs/behavior/chat.md`` §"Slash
    commands" the user types ``/checkpoint`` mid-session; per
    ``docs/behavior/context-menus.md`` §"Checkpoint (gutter chip)" the
    primary action is ``checkpoint.fork`` (creates a new session
    sharing history up to the checkpoint message). This test
    establishes the data-layer invariant the fork action depends on:
    after a checkpoint is recorded, subsequent messages do NOT mutate
    the checkpoint's recorded message_id; the checkpoint correctly
    points to the message it was placed at.
    """
    session_id, first_message = await _seed_session_with_message(connection)
    cp = await create(connection, session_id=session_id, message_id=first_message, label="boundary")
    # Record a few more turns after the checkpoint.
    timestamp = "2026-04-28T12:30:00+00:00"
    for index in range(3):
        await connection.execute(
            "INSERT INTO messages (id, session_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"msg_post_{index}", session_id, "assistant", f"turn {index}", timestamp),
        )
    await connection.commit()
    fetched = await get(connection, cp.id)
    assert fetched is not None
    # The checkpoint still points to the original boundary message;
    # post-checkpoint messages do not perturb it. Fork-from-this-point
    # at the API layer (item 1.10) replays history up to and including
    # `first_message`.
    assert fetched.message_id == first_message
    # And all four messages exist on the session — the checkpoint did
    # not truncate / delete anything (no "restore overwrite" semantic).
    cursor = await connection.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id = ?",
        (session_id,),
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    assert row is not None
    assert int(row[0]) == 4  # one boundary + three post


async def test_create_fails_with_unknown_session_fk(
    connection: aiosqlite.Connection,
) -> None:
    """FK enforcement rejects a checkpoint pointing at a missing session."""
    with pytest.raises(aiosqlite.IntegrityError):
        await create(
            connection,
            session_id="session_missing",
            message_id="msg_missing",
            label="bad",
        )


async def test_create_fails_with_label_above_cap(
    connection: aiosqlite.Connection,
) -> None:
    """The dataclass cap fires before any DB write."""
    session_id, message_id = await _seed_session_with_message(connection)
    with pytest.raises(ValueError, match="≤"):
        await create(
            connection,
            session_id=session_id,
            message_id=message_id,
            label="x" * 10_000,
        )
