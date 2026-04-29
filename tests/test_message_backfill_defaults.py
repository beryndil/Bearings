"""Backfill-default tests for the ``messages`` table (item 1.9 + spec §5).

Per ``docs/model-routing-v1-spec.md`` §5 "Backfill for legacy data":

    Pre-v1 messages don't have these fields. The migration sets them
    best-effort from the session's ``model`` field with
    ``routing_source = 'unknown_legacy'``. Analytics filter these
    out of override-rate calculations.

The migration in item 3.2 will populate what it can; this item
ensures that **right now** the schema's DEFAULT clauses are correct
for the legacy carrier shape — so a row inserted with NULL on every
routing/usage column round-trips cleanly through the dataclass +
read paths + API surface.

Two contracts asserted here:

1. **NULL is the right default for every nullable routing/usage
   column** so an ``unknown_legacy`` row can be inserted by the
   migration with explicit NULLs and the read path doesn't fall
   over.
2. **``advisor_calls_count`` defaults to 0** (per spec §5 verbatim:
   ``ALTER TABLE messages ADD COLUMN advisor_calls_count INTEGER
   DEFAULT 0``). A pre-routing row inserted without supplying the
   column gets ``0``, which is semantically correct ("no advisor
   calls happened") rather than NULL ("advisor concept did not
   exist"). The override-rate aggregator at item 1.8 already filters
   ``unknown_legacy`` rows out so the 0 vs NULL distinction does not
   affect rule-rate math.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from bearings.config.constants import SESSION_KIND_CHAT
from bearings.db import messages as messages_db
from bearings.db import sessions as sessions_db
from bearings.db._id import new_id, now_iso
from bearings.db.connection import load_schema


@pytest.fixture
async def conn(tmp_path: Path):
    db_path = tmp_path / "backfill.db"
    async with aiosqlite.connect(db_path) as connection:
        await load_schema(connection)
        yield connection


async def _new_session(conn: aiosqlite.Connection) -> str:
    s = await sessions_db.create(
        conn,
        kind=SESSION_KIND_CHAT,
        title="t",
        working_dir="/wd",
        model="sonnet",
    )
    return s.id


async def test_legacy_unknown_row_with_null_routing_fields_round_trips(
    conn: aiosqlite.Connection,
) -> None:
    """Insert a pre-v1 assistant row exactly as the item-3.2 migration
    will produce it: NULL on every routing/usage column except
    ``routing_source = 'unknown_legacy'`` + the legacy flat
    ``input_tokens`` / ``output_tokens`` carriers (per spec §5).
    Then read it back through ``messages.get`` and confirm every
    column projects correctly onto the :class:`Message` dataclass."""
    sid = await _new_session(conn)
    message_id = new_id("msg")
    timestamp = now_iso()
    await conn.execute(
        "INSERT INTO messages ("
        "id, session_id, role, content, created_at, "
        "routing_source, input_tokens, output_tokens"
        ") VALUES (?, ?, 'assistant', ?, ?, 'unknown_legacy', ?, ?)",
        (message_id, sid, "legacy answer", timestamp, 1234, 567),
    )
    await conn.commit()
    fetched = await messages_db.get(conn, message_id)
    assert fetched is not None
    assert fetched.role == "assistant"
    # Every routing-decision column NULL — the migration has nothing
    # to populate them with.
    assert fetched.executor_model is None
    assert fetched.advisor_model is None
    assert fetched.effort_level is None
    assert fetched.routing_reason is None
    assert fetched.matched_rule_id is None
    # routing_source carries the spec §5 sentinel so analytics can
    # filter the row out.
    assert fetched.routing_source == "unknown_legacy"
    # Per-model usage NULL (the spec §5 fields don't exist in v0.17).
    assert fetched.executor_input_tokens is None
    assert fetched.executor_output_tokens is None
    assert fetched.advisor_input_tokens is None
    assert fetched.advisor_output_tokens is None
    assert fetched.cache_read_tokens is None
    # ``advisor_calls_count`` carries the schema DEFAULT 0 because
    # the INSERT did not supply it. Spec §5 verbatim ALTER declares
    # the default; the Backfill paragraph relies on it implicitly.
    assert fetched.advisor_calls_count == 0
    # Legacy flat carriers populated by the migration.
    assert fetched.input_tokens == 1234
    assert fetched.output_tokens == 567


async def test_advisor_calls_count_defaults_to_zero_per_spec(
    conn: aiosqlite.Connection,
) -> None:
    """Per spec §5 verbatim ``ALTER TABLE messages ADD COLUMN
    advisor_calls_count INTEGER DEFAULT 0`` — a row inserted without
    naming the column gets the DEFAULT 0."""
    sid = await _new_session(conn)
    message_id = new_id("msg")
    await conn.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at) "
        "VALUES (?, ?, 'user', '?', ?)",
        (message_id, sid, now_iso()),
    )
    await conn.commit()
    fetched = await messages_db.get(conn, message_id)
    assert fetched is not None
    assert fetched.advisor_calls_count == 0


async def test_user_row_leaves_routing_columns_null(
    conn: aiosqlite.Connection,
) -> None:
    """Item 1.7 :func:`bearings.db.messages.insert_user` writes a row
    whose every routing-decision column is NULL — confirms the
    backfill default for the user-row case (the v0.17 → v0.18
    migration treats user rows the same way: no routing data to
    populate)."""
    sid = await _new_session(conn)
    msg = await messages_db.insert_user(conn, session_id=sid, content="hi")
    assert msg.executor_model is None
    assert msg.advisor_model is None
    assert msg.effort_level is None
    assert msg.routing_source is None
    assert msg.routing_reason is None
    assert msg.matched_rule_id is None
    assert msg.executor_input_tokens is None
    assert msg.executor_output_tokens is None
    assert msg.advisor_input_tokens is None
    assert msg.advisor_output_tokens is None
    assert msg.cache_read_tokens is None
    # advisor_calls_count carries DEFAULT 0 per spec §5.
    assert msg.advisor_calls_count == 0
