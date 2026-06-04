"""Session-scoped message-context queries.

Queries that bridge sessions to their paired checklist context or to
pivot messages live here.  Pure read-only — no mutations.
"""

from __future__ import annotations

import aiosqlite

from bearings.db._sessions_base import Session
from bearings.db.sessions_read import _SELECT_SESSION_COLUMNS, _row_to_session


async def is_closed(
    connection: aiosqlite.Connection,
    session_id: str,
) -> bool | None:
    """``True`` / ``False`` per ``closed_at`` state; ``None`` if absent.

    The tri-state return is load-bearing for the prompt-endpoint, which must
    distinguish 404 (session does not exist) from 409 (session closed) per
    behavior doc §"Failure responses".
    """
    cursor = await connection.execute(
        "SELECT closed_at FROM sessions WHERE id = ?",
        (session_id,),
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    if row is None:
        return None
    return row[0] is not None


async def get_kind(
    connection: aiosqlite.Connection,
    session_id: str,
) -> str | None:
    """Return ``sessions.kind`` for ``session_id``; ``None`` if absent."""
    cursor = await connection.execute(
        "SELECT kind FROM sessions WHERE id = ?",
        (session_id,),
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    return None if row is None else str(row[0])


async def get_paired_chat_info(
    connection: aiosqlite.Connection,
    session_id: str,
) -> tuple[str, str] | None:
    """Fetch paired-chat metadata (parent_title, item_label) for a chat session.

    Returns ``None`` when the session is not paired or is absent.  Used by
    the breadcrumb chip per ``docs/behavior/paired-chats.md`` §"From the
    chat side".
    """
    cursor = await connection.execute(
        "SELECT parent.title, item.label "
        "FROM sessions chat "
        "LEFT JOIN checklist_items item ON chat.checklist_item_id = item.id "
        "LEFT JOIN sessions parent ON item.checklist_id = parent.id "
        "WHERE chat.id = ? AND item.id IS NOT NULL",
        (session_id,),
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    if row is None:
        return None
    return (str(row[0]), str(row[1]))


async def get_by_pivot_message_id(
    connection: aiosqlite.Connection,
    pivot_message_id: str,
) -> Session | None:
    """Return the open session spawned from ``pivot_message_id``, or ``None``.

    Used by spawn-from-reply (gap-cycle-03-007) for idempotency: if a
    previous click already spawned a chat for this assistant message, return
    the existing open session rather than creating another.
    """
    cursor = await connection.execute(
        _SELECT_SESSION_COLUMNS + " WHERE pivot_message_id = ? AND closed_at IS NULL",
        (pivot_message_id,),
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    return None if row is None else _row_to_session(row)
