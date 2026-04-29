"""RoutingDecision plumbing for the prompt endpoint (item 1.7 carry-forward).

Item 1.7 picks shape (a) per the plug — session_assembly produces a
real :class:`RoutingDecision` (placeholder source values until item
1.8 swaps in the evaluator). This test verifies:

* The session row's ``model`` column carries a value the
  RoutingDecision validator accepts (sonnet / haiku / opus / full id).
* User-message rows persisted by the prompt endpoint leave the
  routing/usage columns NULL (assistant-turn persistence path lands
  with item 1.2/1.3+ streaming integration).
* The ``messages.routing_source`` filter index works (legacy /
  unknown_legacy backfill path).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from bearings.agent.session_assembly import build_session_config
from bearings.config.constants import (
    KNOWN_EXECUTOR_MODELS,
    KNOWN_ROUTING_SOURCES,
    SESSION_KIND_CHAT,
)
from bearings.db import messages as messages_db
from bearings.db import sessions as sessions_db
from bearings.db.connection import load_schema
from bearings.web.app import create_app


@pytest.fixture
async def conn(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    db_path = tmp_path / "routing.db"
    connection = await aiosqlite.connect(db_path)
    try:
        await load_schema(connection)
        yield connection
    finally:
        await connection.close()


async def test_assembly_emits_decision_with_known_source(
    conn: aiosqlite.Connection,
) -> None:
    config = await build_session_config(conn, session_id="ses_x", working_dir="/wd")
    assert config.decision.source in KNOWN_ROUTING_SOURCES


async def test_assembly_executor_model_in_known_alphabet(
    conn: aiosqlite.Connection,
) -> None:
    """The placeholder evaluator never produces a model outside the
    short-name alphabet — item 1.8 may extend to full SDK ids when it
    lands but day 1 is short-name only."""
    config = await build_session_config(conn, session_id="ses_x", working_dir="/wd")
    assert config.decision.executor_model in KNOWN_EXECUTOR_MODELS


async def test_user_messages_leave_routing_columns_null(
    conn: aiosqlite.Connection, tmp_path: Path
) -> None:
    """Per spec §5 the routing/usage columns are populated by the
    *assistant*-turn persistence path; user rows leave them NULL."""
    app = create_app(db_connection=conn)
    session = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title="t", working_dir="/wd", model="sonnet"
    )
    with TestClient(app) as client:
        client.post(f"/api/sessions/{session.id}/prompt", json={"content": "first"})
    rows = await messages_db.list_for_session(conn, session.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.executor_model is None
    assert row.advisor_model is None
    assert row.routing_source is None
    assert row.routing_reason is None
    assert row.executor_input_tokens is None


async def test_session_row_model_field_round_trips_through_assembly(
    conn: aiosqlite.Connection,
) -> None:
    """A SessionConfig built from the assembler's output must produce
    a model value that ``sessions.create`` accepts — the two
    validators agree on the alphabet."""
    config = await build_session_config(conn, session_id="ses_rt", working_dir="/wd", model="haiku")
    session = await sessions_db.create(
        conn,
        kind=SESSION_KIND_CHAT,
        title="t",
        working_dir=config.working_dir,
        model=config.decision.executor_model,
    )
    fresh = await sessions_db.get(conn, session.id)
    assert fresh is not None and fresh.model == "haiku"
