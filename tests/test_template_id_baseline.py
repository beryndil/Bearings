"""Tests for the ``template_id`` FK + ``template_baseline`` prompt layer (item 622).

Three contract guarantees:

1. **Migration applies + constraint correct.** A fresh DB carries the
   ``sessions.template_id`` column with a ``REFERENCES templates(id) ON
   DELETE SET NULL`` foreign key, and a legacy DB (sessions table created
   before the column shipped) gains it via the ``_ADDED_COLUMNS`` ALTER
   pass.  Deleting the referenced template nulls the back-pointer rather
   than orphaning or cascading the session.
2. **Dataclass round-trip.** ``sessions.create(..., template_id=...)``
   persists and reads back the value through :class:`Session`; omitting
   it leaves the column ``None``.
3. **Endpoint layer.** ``GET /api/sessions/{id}/system_prompt`` emits a
   ``template_baseline`` layer carrying the template's
   ``system_prompt_baseline`` when the session has a ``template_id`` and
   omits the layer when it does not.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bearings.agent.prompt_assembler import LAYER_KIND_TEMPLATE_BASELINE
from bearings.config.constants import SESSION_KIND_CHAT
from bearings.db import sessions as sessions_db
from bearings.db import templates as templates_db
from bearings.db.connection import load_schema
from bearings.web.app import create_app


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    """Per-test fresh DB with the full schema applied."""
    conn = await aiosqlite.connect(tmp_path / "test.db")
    try:
        await load_schema(conn)
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def app_and_db(
    tmp_path: Path,
) -> AsyncIterator[tuple[FastAPI, aiosqlite.Connection]]:
    """FastAPI app wired to a fresh DB connection."""
    conn = await aiosqlite.connect(tmp_path / "api.db")
    try:
        await load_schema(conn)
        app = create_app(db_connection=conn)
        yield app, conn
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# (a) migration applies + column exists with correct constraint
# ---------------------------------------------------------------------------


async def _column_names(connection: aiosqlite.Connection, table: str) -> set[str]:
    """Return the set of column names declared on ``table``."""
    rows = await connection.execute_fetchall(f"PRAGMA table_info({table})")
    return {str(row[1]) for row in rows}


async def test_migration_template_id_column_and_fk_constraint(
    db: aiosqlite.Connection,
) -> None:
    """Fresh schema carries template_id with a SET NULL FK to templates."""
    # Column is present on a fresh DB.
    assert "template_id" in await _column_names(db, "sessions")

    # The foreign key targets templates(id) with ON DELETE SET NULL.
    fk_rows = await db.execute_fetchall("PRAGMA foreign_key_list(sessions)")
    # foreign_key_list columns: id, seq, table, from, to, on_update, on_delete, match.
    template_fks = [row for row in fk_rows if str(row[2]) == "templates"]
    assert len(template_fks) == 1, "expected exactly one FK referencing templates"
    fk = template_fks[0]
    assert str(fk[3]) == "template_id"
    assert str(fk[4]) == "id"
    assert str(fk[6]) == "SET NULL"

    # ON DELETE SET NULL behaviour: deleting the template nulls the
    # back-pointer rather than cascading or orphaning the session.
    template = await templates_db.create(db, name="tpl", model="sonnet")
    session = await sessions_db.create(
        db,
        kind=SESSION_KIND_CHAT,
        title="t",
        working_dir="/wd",
        model="sonnet",
        template_id=template.id,
    )
    assert session.template_id == template.id
    await templates_db.delete(db, template.id)
    refetched = await sessions_db.get(db, session.id)
    assert refetched is not None
    assert refetched.template_id is None


async def test_migration_template_id_added_to_legacy_sessions_db(
    tmp_path: Path,
) -> None:
    """A sessions table predating the column gets template_id via the ALTER pass."""
    conn = await aiosqlite.connect(tmp_path / "legacy.db")
    try:
        # Pre-template_id sessions table — the bootstrap CREATE TABLE IF
        # NOT EXISTS skips on re-init, leaving this legacy shape for the
        # _ADDED_COLUMNS ALTER pass to fix up. Carries the columns the
        # base-schema indexes reference (closed_at, checklist_item_id)
        # so executescript's CREATE INDEX statements don't trip on a
        # missing column before the ALTER pass runs.
        await conn.execute(
            "CREATE TABLE sessions ("
            "id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, "
            "working_dir TEXT NOT NULL, model TEXT NOT NULL, "
            "checklist_item_id INTEGER, closed_at TEXT, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL"
            ")"
        )
        await conn.execute(
            "INSERT INTO sessions (id, kind, title, working_dir, model, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "ses_legacy",
                "chat",
                "legacy",
                "/wd",
                "sonnet",
                "2026-04-28T00:00:00+00:00",
                "2026-04-28T00:00:00+00:00",
            ),
        )
        await conn.commit()

        await load_schema(conn)

        assert "template_id" in await _column_names(conn, "sessions")
        rows = list(
            await conn.execute_fetchall(
                "SELECT template_id FROM sessions WHERE id = ?", ("ses_legacy",)
            )
        )
        assert len(rows) == 1
        assert rows[0][0] is None
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# (b) Session dataclass round-trips template_id
# ---------------------------------------------------------------------------


async def test_session_dataclass_round_trips_template_id(
    db: aiosqlite.Connection,
) -> None:
    """create(template_id=...) persists and reads back; omitting it yields None."""
    template = await templates_db.create(db, name="round-trip", model="sonnet")

    with_template = await sessions_db.create(
        db,
        kind=SESSION_KIND_CHAT,
        title="with",
        working_dir="/wd",
        model="sonnet",
        template_id=template.id,
    )
    assert with_template.template_id == template.id
    fetched = await sessions_db.get(db, with_template.id)
    assert fetched is not None
    assert fetched.template_id == template.id

    without_template = await sessions_db.create(
        db,
        kind=SESSION_KIND_CHAT,
        title="without",
        working_dir="/wd",
        model="sonnet",
    )
    assert without_template.template_id is None
    fetched_none = await sessions_db.get(db, without_template.id)
    assert fetched_none is not None
    assert fetched_none.template_id is None


# ---------------------------------------------------------------------------
# (c) system_prompt endpoint emits / omits the template_baseline layer
# ---------------------------------------------------------------------------


async def test_system_prompt_emits_template_baseline_when_template_id_set(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Endpoint emits a template_baseline layer carrying the template body."""
    app, conn = app_and_db
    baseline = "You are bound by the executor charter."
    template = await templates_db.create(
        conn,
        name="exec-template",
        model="sonnet",
        system_prompt_baseline=baseline,
    )
    session = await sessions_db.create(
        conn,
        kind=SESSION_KIND_CHAT,
        title="t",
        working_dir="/nonexistent",
        model="sonnet",
        template_id=template.id,
    )
    with TestClient(app) as client:
        resp = client.get(f"/api/sessions/{session.id}/system_prompt")
    assert resp.status_code == 200
    layers = resp.json()["layers"]
    template_layers = [layer for layer in layers if layer["kind"] == LAYER_KIND_TEMPLATE_BASELINE]
    assert len(template_layers) == 1
    assert template_layers[0]["body"] == baseline
    assert template_layers[0]["source_path"] is None


async def test_system_prompt_omits_template_baseline_when_template_id_null(
    app_and_db: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """Endpoint omits the layer entirely for a session with no template_id."""
    app, conn = app_and_db
    session = await sessions_db.create(
        conn,
        kind=SESSION_KIND_CHAT,
        title="t",
        working_dir="/nonexistent",
        model="sonnet",
    )
    with TestClient(app) as client:
        resp = client.get(f"/api/sessions/{session.id}/system_prompt")
    assert resp.status_code == 200
    kinds = [layer["kind"] for layer in resp.json()["layers"]]
    assert LAYER_KIND_TEMPLATE_BASELINE not in kinds
