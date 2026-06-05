"""Field-update and summary-close operations for the sessions table.

Separated from ``sessions_write`` so each file stays under the 400-line cap.
update_fields, update_title, update_model, update_routing_decision,
update_permission_mode, and close_with_summary live here.
"""

from __future__ import annotations

import aiosqlite

from bearings.config.constants import (
    KNOWN_EFFORT_LEVELS,
    KNOWN_SDK_PERMISSION_MODES,
    SESSION_CLOSING_SUMMARY_MAX_LENGTH,
    SESSION_CLOSING_SUMMARY_MIN_LENGTH,
    SESSION_TITLE_MAX_LENGTH,
)
from bearings.db._id import now_iso
from bearings.db._sessions_base import (
    _SENTINEL,
    Session,
    _apply_budget_field,
    _apply_description_field,
    _apply_instructions_field,
    _apply_title_field,
    _is_known_model,
)
from bearings.db.sessions_read import get


async def update_fields(
    connection: aiosqlite.Connection,
    session_id: str,
    *,
    title: object = _SENTINEL,
    description: object = _SENTINEL,
    max_budget_usd: object = _SENTINEL,
    session_instructions: object = _SENTINEL,
) -> Session | None:
    """Patch arbitrary mutable session columns in one round-trip.

    Only keyword arguments whose value is not ``_SENTINEL`` are written
    (true PATCH semantics).  ``title`` must be a non-empty string;
    nullable columns may be passed as ``None`` to clear them.  Returns the
    refreshed :class:`Session` row, or ``None`` when no row matches.
    """
    existing = await get(connection, session_id)
    if existing is None:
        return None
    assignments: list[str] = []
    params: list[object] = []
    _apply_title_field(title, assignments, params)
    _apply_description_field(description, assignments, params)
    _apply_budget_field(max_budget_usd, assignments, params)
    _apply_instructions_field(session_instructions, assignments, params)
    if not assignments:
        return existing
    timestamp = now_iso()
    assignments.append("updated_at = ?")
    params.append(timestamp)
    params.append(session_id)
    await connection.execute(
        f"UPDATE sessions SET {', '.join(assignments)} WHERE id = ?",
        params,
    )
    await connection.commit()
    return await get(connection, session_id)


async def update_title(
    connection: aiosqlite.Connection,
    session_id: str,
    *,
    title: str,
) -> Session | None:
    """Replace ``title``; returns the new row or ``None`` if absent."""
    if not title:
        raise ValueError("update_title: title must be non-empty")
    if len(title) > SESSION_TITLE_MAX_LENGTH:
        raise ValueError(
            f"update_title: title must be ≤ {SESSION_TITLE_MAX_LENGTH} chars (got {len(title)})"
        )
    existing = await get(connection, session_id)
    if existing is None:
        return None
    timestamp = now_iso()
    await connection.execute(
        "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
        (title, timestamp, session_id),
    )
    await connection.commit()
    return await get(connection, session_id)


async def update_model(
    connection: aiosqlite.Connection,
    session_id: str,
    *,
    model: str,
) -> Session | None:
    """Replace ``model``; returns the new row or ``None`` if absent.

    Backs ``PATCH /api/sessions/{id}/model``.  422-able via ``ValueError``
    on unknown model names.
    """
    if not _is_known_model(model):
        raise ValueError(f"update_model: model {model!r} not recognised")
    existing = await get(connection, session_id)
    if existing is None:
        return None
    timestamp = now_iso()
    await connection.execute(
        "UPDATE sessions SET model = ?, updated_at = ? WHERE id = ?",
        (model, timestamp, session_id),
    )
    await connection.commit()
    return await get(connection, session_id)


async def update_routing_decision(
    connection: aiosqlite.Connection,
    session_id: str,
    *,
    routing_advisor_model: str | None,
    routing_advisor_max_uses: int,
    routing_effort_level: str,
) -> Session | None:
    """Replace the routing-decision projection; returns the new row or ``None``."""
    if routing_advisor_model is not None and not _is_known_model(routing_advisor_model):
        raise ValueError(
            f"update_routing_decision: routing_advisor_model "
            f"{routing_advisor_model!r} not recognised"
        )
    if routing_advisor_max_uses < 0:
        raise ValueError(
            f"update_routing_decision: routing_advisor_max_uses must be ≥ 0 "
            f"(got {routing_advisor_max_uses})"
        )
    if routing_effort_level not in KNOWN_EFFORT_LEVELS:
        raise ValueError(
            f"update_routing_decision: routing_effort_level "
            f"{routing_effort_level!r} not in {sorted(KNOWN_EFFORT_LEVELS)}"
        )
    existing = await get(connection, session_id)
    if existing is None:
        return None
    timestamp = now_iso()
    await connection.execute(
        "UPDATE sessions SET "
        "routing_advisor_model = ?, routing_advisor_max_uses = ?, "
        "routing_effort_level = ?, updated_at = ? WHERE id = ?",
        (
            routing_advisor_model,
            routing_advisor_max_uses,
            routing_effort_level,
            timestamp,
            session_id,
        ),
    )
    await connection.commit()
    return await get(connection, session_id)


async def update_permission_mode(
    connection: aiosqlite.Connection,
    session_id: str,
    *,
    permission_mode: str | None,
) -> Session | None:
    """Replace ``permission_mode``; ``None`` clears the column.

    Backs ``PATCH /api/sessions/{id}/permission_mode`` (item 3.3).
    ``ValueError`` on unknown mode strings.
    """
    if permission_mode is not None and permission_mode not in KNOWN_SDK_PERMISSION_MODES:
        raise ValueError(
            f"update_permission_mode: permission_mode {permission_mode!r} not in "
            f"{sorted(KNOWN_SDK_PERMISSION_MODES)}"
        )
    existing = await get(connection, session_id)
    if existing is None:
        return None
    timestamp = now_iso()
    await connection.execute(
        "UPDATE sessions SET permission_mode = ?, updated_at = ? WHERE id = ?",
        (permission_mode, timestamp, session_id),
    )
    await connection.commit()
    return await get(connection, session_id)


async def set_classified(
    connection: aiosqlite.Connection,
    session_id: str,
    *,
    classified: bool,
) -> Session | None:
    """Persist the classification flag for a session (T2-07).

    Backs ``POST /api/sessions/{id}/spawn_classify``.  Sets
    ``classified = 1`` (or ``0``) and bumps ``updated_at``.  Returns the
    refreshed :class:`Session` row, or ``None`` when no row matches.
    """
    existing = await get(connection, session_id)
    if existing is None:
        return None
    timestamp = now_iso()
    await connection.execute(
        "UPDATE sessions SET classified = ?, updated_at = ? WHERE id = ?",
        (1 if classified else 0, timestamp, session_id),
    )
    await connection.commit()
    return await get(connection, session_id)


async def close_with_summary(
    connection: aiosqlite.Connection,
    session_id: str,
    *,
    summary: str,
) -> Session | None:
    """Stamp ``closed_at`` AND persist the agent-authored ``closing_summary``.

    Backs the ``close_session`` MCP tool.  Idempotent no-op when the row is
    already closed — returns ``None`` instead of overwriting an earlier summary.
    Returns ``None`` also when the row is missing.  ``ValueError`` on summary
    bounds violations.
    """
    length = len(summary)
    if length < SESSION_CLOSING_SUMMARY_MIN_LENGTH:
        raise ValueError(
            f"close_with_summary: summary must be ≥ "
            f"{SESSION_CLOSING_SUMMARY_MIN_LENGTH} chars (got {length})"
        )
    if length > SESSION_CLOSING_SUMMARY_MAX_LENGTH:
        raise ValueError(
            f"close_with_summary: summary must be ≤ "
            f"{SESSION_CLOSING_SUMMARY_MAX_LENGTH} chars (got {length})"
        )
    existing = await get(connection, session_id)
    if existing is None:
        return None
    if existing.closed_at is not None:
        return None
    timestamp = now_iso()
    await connection.execute(
        "UPDATE sessions SET closed_at = ?, closing_summary = ?, updated_at = ? WHERE id = ?",
        (timestamp, summary, timestamp, session_id),
    )
    await connection.commit()
    return await get(connection, session_id)
