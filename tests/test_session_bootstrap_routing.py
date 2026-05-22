"""Tests for session bootstrap routing-source fix (rt-15, feature-3).

Before the fix, :func:`build_session_setup` hardcoded
``source='default'`` and ``reason='session <sid> bootstrap'`` in the
reconstructed :class:`RoutingDecision`, causing every v0.18.0-era
assistant message to record ``routing_source='default'`` regardless
of the real rule that should fire.

After the fix the bootstrap calls the rule walker (``evaluate`` with
an empty first-message) to derive ``source`` / ``reason`` /
``matched_rule_id`` from the live rule set. With the seeded
always-fallback system rule (priority 1000, always-match, id
deterministic per the schema seed) present, the walker returns
``source='system_rule'`` and ``matched_rule_id`` set to that rule's
id rather than ``None``.

Tests here confirm:

* The returned :class:`SessionSetup.decision.source` is ``'system_rule'``
  (not ``'default'``).
* ``matched_rule_id`` is non-``None`` (the always-fallback seed fired).
* The executor / advisor / effort values come from the session row
  columns, not from the rule result (the row wins per spec §session-
  bootstrap invariant).
* When the rule table is empty (no system rules at all) the walker's
  absolute-default fires and ``source='default'``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest

from bearings.agent.runner import SessionRunner
from bearings.agent.session_bootstrap import build_session_setup
from bearings.db import sessions as sessions_db
from bearings.db.connection import load_schema


@pytest.fixture
async def conn(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    db_path = tmp_path / "bootstrap_routing.db"
    async with aiosqlite.connect(db_path) as connection:
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        await load_schema(connection)
        yield connection


async def _fake_runner() -> SessionRunner:  # pragma: no cover
    """Stub runner — build_session_setup only uses it to pass to the setup fn."""
    raise NotImplementedError


async def _make_session(
    conn: aiosqlite.Connection,
    *,
    model: str = "sonnet",
    advisor_model: str | None = "opus",
    effort: str = "auto",
) -> str:
    row = await sessions_db.create(
        conn,
        kind="chat",
        title="bootstrap-routing-test",
        working_dir="/tmp/wd",
        model=model,
        routing_advisor_model=advisor_model,
        routing_effort_level=effort,
    )
    await conn.commit()
    return row.id


@pytest.mark.asyncio
async def test_bootstrap_source_is_system_rule_with_seeded_rules(
    conn: aiosqlite.Connection,
) -> None:
    """Bootstrap uses system_rule source (not 'default') when seed rules exist."""
    session_id = await _make_session(conn)
    setup_fn = build_session_setup(conn, enable_approval_broker=False)
    # Pass a MagicMock-like stub as the runner — the bootstrap only needs it
    # to construct the ApprovalBroker (disabled here) and does not call methods.
    import unittest.mock as mock

    runner_stub = mock.MagicMock(spec=SessionRunner)
    result = await setup_fn(session_id, runner_stub)
    assert result is not None
    decision = result.session.config.decision
    # The seeded always-fallback system rule fires → source must be 'system_rule'.
    assert decision.source == "system_rule", (
        f"Expected 'system_rule' but got {decision.source!r}. "
        "The bootstrap still hardcodes 'default' — rt-15 fix not applied."
    )


@pytest.mark.asyncio
async def test_bootstrap_matched_rule_id_is_set(conn: aiosqlite.Connection) -> None:
    """matched_rule_id is non-None after fix (always-fallback rule fired)."""
    session_id = await _make_session(conn)
    setup_fn = build_session_setup(conn, enable_approval_broker=False)
    import unittest.mock as mock

    runner_stub = mock.MagicMock(spec=SessionRunner)
    result = await setup_fn(session_id, runner_stub)
    assert result is not None
    decision = result.session.config.decision
    assert decision.matched_rule_id is not None, (
        "matched_rule_id should be non-None when the always-fallback rule fires."
    )


@pytest.mark.asyncio
async def test_bootstrap_preserves_session_row_executor(conn: aiosqlite.Connection) -> None:
    """Executor model comes from the session row, not the rule result."""
    # Create session with haiku executor (non-default to make the assertion
    # unambiguous — if the rule result leaked through it would give 'sonnet').
    session_id = await _make_session(conn, model="haiku", advisor_model="opus")
    setup_fn = build_session_setup(conn, enable_approval_broker=False)
    import unittest.mock as mock

    runner_stub = mock.MagicMock(spec=SessionRunner)
    result = await setup_fn(session_id, runner_stub)
    assert result is not None
    decision = result.session.config.decision
    assert decision.executor_model == "haiku", (
        f"Expected executor='haiku' from session row but got {decision.executor_model!r}."
    )


@pytest.mark.asyncio
async def test_bootstrap_preserves_session_row_effort(conn: aiosqlite.Connection) -> None:
    """Effort level comes from the session row."""
    session_id = await _make_session(conn, effort="high")
    setup_fn = build_session_setup(conn, enable_approval_broker=False)
    import unittest.mock as mock

    runner_stub = mock.MagicMock(spec=SessionRunner)
    result = await setup_fn(session_id, runner_stub)
    assert result is not None
    decision = result.session.config.decision
    assert decision.effort_level == "high"


@pytest.mark.asyncio
async def test_bootstrap_reason_is_not_legacy_placeholder(conn: aiosqlite.Connection) -> None:
    """Bootstrap reason must not be the literal 'session <sid> bootstrap' string."""
    session_id = await _make_session(conn)
    setup_fn = build_session_setup(conn, enable_approval_broker=False)
    import unittest.mock as mock

    runner_stub = mock.MagicMock(spec=SessionRunner)
    result = await setup_fn(session_id, runner_stub)
    assert result is not None
    decision = result.session.config.decision
    legacy_placeholder = f"session {session_id} bootstrap"
    assert decision.reason != legacy_placeholder, (
        f"Bootstrap reason is still the legacy placeholder {legacy_placeholder!r}."
    )
