"""Core session write operations — create, import, delete, close, reopen, lifecycle.

Field-specific updates (update_fields, update_title, update_model, etc.) and
close_with_summary live in ``sessions_update`` to keep this file under the
400-line cap.
"""

from __future__ import annotations

import aiosqlite

from bearings.config.constants import SESSION_ID_PREFIX
from bearings.db._id import new_id, now_iso
from bearings.db._sessions_base import Session
from bearings.db.sessions_read import get


async def create(
    connection: aiosqlite.Connection,
    *,
    kind: str,
    title: str,
    working_dir: str,
    model: str,
    description: str | None = None,
    session_instructions: str | None = None,
    permission_mode: str | None = None,
    max_budget_usd: float | None = None,
    checklist_item_id: int | None = None,
    routing_advisor_model: str | None = None,
    routing_advisor_max_uses: int = 5,
    routing_effort_level: str = "auto",
    pivot_message_id: str | None = None,
    parent_session_id: str | None = None,
    template_id: int | None = None,
) -> Session:
    """Insert a fresh session row.

    The id is generated as ``ses_<32-hex>``.  Validation runs via a
    phantom :class:`Session` construct before the INSERT so a bad shape never
    touches the DB.  ``pivot_message_id`` / ``parent_session_id`` are set
    only by the spawn-from-reply route (gap-cycle-03-007).  ``template_id``
    (item 622) is set only by the template-instantiate route.
    """
    timestamp = now_iso()
    session_id = new_id(SESSION_ID_PREFIX)
    Session(
        id=session_id,
        kind=kind,
        title=title,
        description=description,
        session_instructions=session_instructions,
        working_dir=working_dir,
        model=model,
        permission_mode=permission_mode,
        max_budget_usd=max_budget_usd,
        total_cost_usd=0.0,
        message_count=0,
        last_context_pct=None,
        last_context_tokens=None,
        last_context_max=None,
        pinned=False,
        error_pending=False,
        checklist_item_id=checklist_item_id,
        created_at=timestamp,
        updated_at=timestamp,
        last_viewed_at=None,
        last_completed_at=None,
        closed_at=None,
        closing_summary=None,
        routing_advisor_model=routing_advisor_model,
        routing_advisor_max_uses=routing_advisor_max_uses,
        routing_effort_level=routing_effort_level,
        pivot_message_id=pivot_message_id,
        parent_session_id=parent_session_id,
        template_id=template_id,
    )
    await connection.execute(
        "INSERT INTO sessions "
        "(id, kind, title, description, session_instructions, working_dir, model, "
        "permission_mode, max_budget_usd, checklist_item_id, "
        "routing_advisor_model, routing_advisor_max_uses, routing_effort_level, "
        "pivot_message_id, parent_session_id, template_id, "
        "created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            kind,
            title,
            description,
            session_instructions,
            working_dir,
            model,
            permission_mode,
            max_budget_usd,
            checklist_item_id,
            routing_advisor_model,
            routing_advisor_max_uses,
            routing_effort_level,
            pivot_message_id,
            parent_session_id,
            template_id,
            timestamp,
            timestamp,
        ),
    )
    await connection.commit()
    fetched = await get(connection, session_id)
    if fetched is None:  # pragma: no cover — INSERT just succeeded
        raise RuntimeError(f"sessions.create: row {session_id!r} vanished after INSERT")
    return fetched


async def import_session(
    connection: aiosqlite.Connection,
    *,
    session_id: str,
    kind: str,
    title: str,
    description: str | None,
    session_instructions: str | None,
    working_dir: str,
    model: str,
    permission_mode: str | None,
    max_budget_usd: float | None,
    total_cost_usd: float,
    message_count: int,
    last_context_pct: float | None,
    last_context_tokens: int | None,
    last_context_max: int | None,
    pinned: bool,
    closed_at: str | None,
    closing_summary: str | None,
    created_at: str,
    updated_at: str,
    last_viewed_at: str | None,
    last_completed_at: str | None,
) -> Session:
    """Insert a session row preserving the original id and timestamps.

    Used exclusively by ``POST /api/sessions/import``.  ``checklist_item_id``
    and ``template_id`` are always ``None`` on import; routing-decision
    columns default to schema defaults (``NULL``, ``5``, ``'auto'``).
    ``error_pending`` is unconditionally cleared.
    """
    Session(
        id=session_id,
        kind=kind,
        title=title,
        description=description,
        session_instructions=session_instructions,
        working_dir=working_dir,
        model=model,
        permission_mode=permission_mode,
        max_budget_usd=max_budget_usd,
        total_cost_usd=total_cost_usd,
        message_count=message_count,
        last_context_pct=last_context_pct,
        last_context_tokens=last_context_tokens,
        last_context_max=last_context_max,
        pinned=pinned,
        error_pending=False,
        checklist_item_id=None,
        created_at=created_at,
        updated_at=updated_at,
        last_viewed_at=last_viewed_at,
        last_completed_at=last_completed_at,
        closed_at=closed_at,
        closing_summary=closing_summary,
        routing_advisor_model=None,
        routing_advisor_max_uses=5,
        routing_effort_level="auto",
        pivot_message_id=None,
        parent_session_id=None,
        template_id=None,
    )
    await connection.execute(
        "INSERT INTO sessions "
        "(id, kind, title, description, session_instructions, working_dir, model, "
        "permission_mode, max_budget_usd, total_cost_usd, message_count, "
        "last_context_pct, last_context_tokens, last_context_max, "
        "pinned, error_pending, checklist_item_id, "
        "closed_at, closing_summary, created_at, updated_at, "
        "last_viewed_at, last_completed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, "
        "?, ?, ?, ?, ?, ?)",
        (
            session_id,
            kind,
            title,
            description,
            session_instructions,
            working_dir,
            model,
            permission_mode,
            max_budget_usd,
            total_cost_usd,
            message_count,
            last_context_pct,
            last_context_tokens,
            last_context_max,
            pinned,
            closed_at,
            closing_summary,
            created_at,
            updated_at,
            last_viewed_at,
            last_completed_at,
        ),
    )
    await connection.commit()
    fetched = await get(connection, session_id)
    if fetched is None:  # pragma: no cover — INSERT just succeeded
        raise RuntimeError(f"sessions.import_session: row {session_id!r} vanished after INSERT")
    return fetched


async def delete(
    connection: aiosqlite.Connection,
    session_id: str,
) -> bool:
    """Delete one session row; cascades to messages + checkpoints + tags.

    ``checklist_items.chat_session_id`` carries ON DELETE SET NULL so deleting
    a paired chat clears the item-side pointer without orphaning the item.
    """
    cursor = await connection.execute(
        "DELETE FROM sessions WHERE id = ?",
        (session_id,),
    )
    rowcount = cursor.rowcount
    await cursor.close()
    await connection.commit()
    return rowcount > 0


async def close(
    connection: aiosqlite.Connection,
    session_id: str,
) -> Session | None:
    """Stamp ``closed_at`` to now (idempotent — re-stamps with new value)."""
    existing = await get(connection, session_id)
    if existing is None:
        return None
    timestamp = now_iso()
    await connection.execute(
        "UPDATE sessions SET closed_at = ?, updated_at = ? WHERE id = ?",
        (timestamp, timestamp, session_id),
    )
    await connection.commit()
    return await get(connection, session_id)


async def reopen(
    connection: aiosqlite.Connection,
    session_id: str,
) -> Session | None:
    """Clear ``closed_at`` (the inverse of :func:`close`).

    Per ``docs/behavior/paired-chats.md`` §"Reopen semantics".
    """
    existing = await get(connection, session_id)
    if existing is None:
        return None
    timestamp = now_iso()
    await connection.execute(
        "UPDATE sessions SET closed_at = NULL, updated_at = ? WHERE id = ?",
        (timestamp, session_id),
    )
    await connection.commit()
    return await get(connection, session_id)


async def mark_viewed(
    connection: aiosqlite.Connection,
    session_id: str,
) -> Session | None:
    """Stamp ``last_viewed_at`` to now.

    Called by ``POST /api/sessions/{id}/viewed``.  The broadcast that
    follows clears the unviewed-dot on any other open tab / window.
    """
    existing = await get(connection, session_id)
    if existing is None:
        return None
    timestamp = now_iso()
    await connection.execute(
        "UPDATE sessions SET last_viewed_at = ?, updated_at = ? WHERE id = ?",
        (timestamp, timestamp, session_id),
    )
    await connection.commit()
    return await get(connection, session_id)


async def update_pinned(
    connection: aiosqlite.Connection,
    session_id: str,
    *,
    pinned: bool,
) -> Session | None:
    """Set or clear the ``pinned`` flag; returns the updated row or ``None`` if absent."""
    existing = await get(connection, session_id)
    if existing is None:
        return None
    await connection.execute(
        "UPDATE sessions SET pinned = ?, updated_at = ? WHERE id = ?",
        (1 if pinned else 0, now_iso(), session_id),
    )
    await connection.commit()
    return await get(connection, session_id)


async def add_to_total_cost(
    connection: aiosqlite.Connection,
    session_id: str,
    delta_usd: float,
) -> None:
    """Atomically add ``delta_usd`` to the session row's ``total_cost_usd``.

    Called by :func:`bearings.agent.persistence.persist_assistant_turn`.
    ``delta_usd`` ≤ 0 is a no-op.  ``updated_at`` is intentionally NOT bumped
    — cost is a derived rollup, not a user-visible content mutation.
    """
    if delta_usd <= 0:
        return
    await connection.execute(
        "UPDATE sessions SET total_cost_usd = total_cost_usd + ? WHERE id = ?",
        (float(delta_usd), session_id),
    )
    await connection.commit()


async def set_error_pending(
    connection: aiosqlite.Connection,
    session_id: str,
    value: bool,
) -> Session | None:
    """Set or clear the ``error_pending`` flag; returns the refreshed row."""
    existing = await get(connection, session_id)
    if existing is None:
        return None
    await connection.execute(
        "UPDATE sessions SET error_pending = ?, updated_at = ? WHERE id = ?",
        (1 if value else 0, now_iso(), session_id),
    )
    await connection.commit()
    return await get(connection, session_id)
