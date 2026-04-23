"""Checkpoint table operations (Phase 7 of docs/context-menu-plan.md).

A checkpoint anchors a named reference to a specific message in a
session. Three consumers drive the shape of this module:

  * The gutter-chip renderer wants every checkpoint for one session,
    newest first — hence `list_checkpoints` ORDER BY created_at DESC,
    backed by the (session_id, created_at) index from migration 0024.
  * The menu handlers for `session.fork.from_checkpoint` and
    `message.fork.from_here` want a single checkpoint row they can
    translate into an `import_session`-style remap — hence
    `get_checkpoint` returning a full row or None.
  * The CRUD endpoints want a minimal surface: create / delete. No
    partial-update path exists because a checkpoint's label is the
    only mutable field and the UI re-creates on rename today; we can
    grow an `update_checkpoint` helper when a real rename flow lands.

Returns dict rows (with keys matching column names) rather than a
typed model so the HTTP layer can pass them straight to Pydantic. The
connection-commit-then-read pattern mirrors `_checklists.create_checklist`:
commit the write first, then re-fetch through `get_checkpoint` so the
caller always sees the persisted row.
"""

from __future__ import annotations

from typing import Any

import aiosqlite

from bearings.db._common import _new_id, _now

CHECKPOINT_COLS = "id, session_id, message_id, label, created_at"


async def create_checkpoint(
    conn: aiosqlite.Connection,
    session_id: str,
    *,
    message_id: str | None,
    label: str | None = None,
) -> dict[str, Any]:
    """Insert a new checkpoint row and return it.

    `message_id` is required at the public-API level (the UI always
    anchors at a concrete message), but typed as Optional here so a
    reorg-dropped message can clear the anchor via direct DB mutation
    without needing a separate helper. The FK is ON DELETE SET NULL so
    a message delete automatically hollows out the anchor — the row
    stays alive as a session-level label.

    Raises sqlite3.IntegrityError if `session_id` doesn't exist (FK
    violation). Callers should have already verified the session; we
    don't duplicate the check because the handler layer owns 404
    translation.
    """
    checkpoint_id = _new_id()
    now = _now()
    await conn.execute(
        f"INSERT INTO checkpoints ({CHECKPOINT_COLS}) VALUES (?, ?, ?, ?, ?)",
        (checkpoint_id, session_id, message_id, label, now),
    )
    await conn.commit()
    row = await get_checkpoint(conn, checkpoint_id)
    assert row is not None  # just inserted
    return row


async def get_checkpoint(conn: aiosqlite.Connection, checkpoint_id: str) -> dict[str, Any] | None:
    """Fetch a single checkpoint by id, or None if not found."""
    async with conn.execute(
        f"SELECT {CHECKPOINT_COLS} FROM checkpoints WHERE id = ?",
        (checkpoint_id,),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row is not None else None


async def list_checkpoints(conn: aiosqlite.Connection, session_id: str) -> list[dict[str, Any]]:
    """Every checkpoint for a session, newest first.

    Ordered by `created_at DESC` to match the gutter-chip UX (latest
    anchor shown at the top of the list). The (session_id, created_at)
    index from migration 0024 serves this query directly — SQLite will
    walk the index backward and stream results without a sort step.
    """
    async with conn.execute(
        f"SELECT {CHECKPOINT_COLS} FROM checkpoints "
        "WHERE session_id = ? ORDER BY created_at DESC, id DESC",
        (session_id,),
    ) as cursor:
        return [dict(row) async for row in cursor]


async def delete_checkpoint(conn: aiosqlite.Connection, checkpoint_id: str) -> bool:
    """Delete a checkpoint by id. Returns True if a row was removed."""
    cursor = await conn.execute("DELETE FROM checkpoints WHERE id = ?", (checkpoint_id,))
    await conn.commit()
    return cursor.rowcount > 0
