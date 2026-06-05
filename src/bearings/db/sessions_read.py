"""Read-only session queries — get, exists, list_all, list_paged.

Also holds the SQL column-select strings, row-to-dataclass mapper, and the
filter-SQL builder shared by list_all / list_paged.  Write operations live
in ``sessions_write`` and ``sessions_update``.
"""

from __future__ import annotations

import aiosqlite

from bearings.config.constants import SESSIONS_MAX_PAGE_SIZE
from bearings.db._sessions_base import (
    Session,
    _append_section_filter,
    _append_severity_filter,
    _append_tag_ids_filter,
    _validate_list_all_args,
)

# ---------------------------------------------------------------------------
# SQL column-select strings
# ---------------------------------------------------------------------------

_SELECT_SESSION_COLUMNS = (
    "SELECT id, kind, title, description, session_instructions, working_dir, model, "
    "permission_mode, max_budget_usd, total_cost_usd, message_count, "
    "last_context_pct, last_context_tokens, last_context_max, pinned, error_pending, "
    "checklist_item_id, created_at, updated_at, last_viewed_at, last_completed_at, "
    "closed_at, closing_summary, "
    "routing_advisor_model, routing_advisor_max_uses, routing_effort_level, "
    "pivot_message_id, parent_session_id, template_id, classified "
    "FROM sessions"
)

_SELECT_SESSION_COLUMNS_DISTINCT = (
    "SELECT DISTINCT sessions.id, sessions.kind, sessions.title, sessions.description, "
    "sessions.session_instructions, sessions.working_dir, sessions.model, "
    "sessions.permission_mode, sessions.max_budget_usd, sessions.total_cost_usd, "
    "sessions.message_count, sessions.last_context_pct, sessions.last_context_tokens, "
    "sessions.last_context_max, sessions.pinned, sessions.error_pending, "
    "sessions.checklist_item_id, sessions.created_at, sessions.updated_at, "
    "sessions.last_viewed_at, sessions.last_completed_at, sessions.closed_at, "
    "sessions.closing_summary, "
    "sessions.routing_advisor_model, sessions.routing_advisor_max_uses, "
    "sessions.routing_effort_level, "
    "sessions.pivot_message_id, sessions.parent_session_id, "
    "sessions.template_id, sessions.classified FROM sessions"
)


# ---------------------------------------------------------------------------
# Row mapper helpers
# ---------------------------------------------------------------------------


def _opt_str(v: object) -> str | None:
    """Return ``None`` when ``v`` is ``None``, otherwise ``str(v)``."""
    return None if v is None else str(v)


def _opt_int(v: object) -> int | None:
    """Return ``None`` when ``v`` is ``None``, otherwise ``int(str(v))``."""
    return None if v is None else int(str(v))


def _opt_float(v: object) -> float | None:
    """Return ``None`` when ``v`` is ``None``, otherwise ``float(str(v))``."""
    return None if v is None else float(str(v))


def _row_to_session(row: aiosqlite.Row | tuple[object, ...]) -> Session:
    """Translate a raw SELECT tuple into a validated :class:`Session`."""
    return Session(
        id=str(row[0]),
        kind=str(row[1]),
        title=str(row[2]),
        description=_opt_str(row[3]),
        session_instructions=_opt_str(row[4]),
        working_dir=str(row[5]),
        model=str(row[6]),
        permission_mode=_opt_str(row[7]),
        max_budget_usd=_opt_float(row[8]),
        total_cost_usd=float(str(row[9])),
        message_count=int(str(row[10])),
        last_context_pct=_opt_float(row[11]),
        last_context_tokens=_opt_int(row[12]),
        last_context_max=_opt_int(row[13]),
        pinned=bool(int(str(row[14]))),
        error_pending=bool(int(str(row[15]))),
        checklist_item_id=_opt_int(row[16]),
        created_at=str(row[17]),
        updated_at=str(row[18]),
        last_viewed_at=_opt_str(row[19]),
        last_completed_at=_opt_str(row[20]),
        closed_at=_opt_str(row[21]),
        closing_summary=_opt_str(row[22]),
        routing_advisor_model=_opt_str(row[23]),
        routing_advisor_max_uses=int(str(row[24])),
        routing_effort_level=str(row[25]),
        pivot_message_id=_opt_str(row[26]),
        parent_session_id=_opt_str(row[27]),
        template_id=_opt_int(row[28]),
        classified=bool(int(str(row[29] if row[29] is not None else 0))),
    )


# ---------------------------------------------------------------------------
# Filter-SQL builder
# ---------------------------------------------------------------------------


def _build_filter_sql(
    kind: str | None,
    include_closed: bool,
    tag_ids: tuple[int, ...] | None,
    tag_ids_project: tuple[int, ...] | None,
    tag_ids_severity: tuple[int, ...] | None,
    tag_ids_other: tuple[int, ...] | None,
    severity_none: bool,
) -> tuple[str, str, list[object]]:
    """Build the JOIN, WHERE, and positional args for the session-list filters.

    Returns ``(join_clause, where_clause, args)`` shared by :func:`list_all`
    and :func:`list_paged`.
    """
    clauses: list[str] = []
    args: list[object] = []
    if kind is not None:
        clauses.append("sessions.kind = ?")
        args.append(kind)
    if not include_closed:
        clauses.append("sessions.closed_at IS NULL")
    _append_tag_ids_filter(tag_ids, clauses, args)
    _append_section_filter(tag_ids_project, clauses, args)
    _append_severity_filter(severity_none, tag_ids_severity, clauses, args)
    _append_section_filter(tag_ids_other, clauses, args)
    join = (
        " INNER JOIN session_tags ON session_tags.session_id = sessions.id"
        if tag_ids is not None
        else ""
    )
    where = "" if not clauses else " WHERE " + " AND ".join(clauses)
    return join, where, args


# ---------------------------------------------------------------------------
# Read queries
# ---------------------------------------------------------------------------


async def get(
    connection: aiosqlite.Connection,
    session_id: str,
) -> Session | None:
    """Fetch one session by id; ``None`` if absent."""
    cursor = await connection.execute(
        _SELECT_SESSION_COLUMNS + " WHERE id = ?",
        (session_id,),
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    return None if row is None else _row_to_session(row)


async def exists(
    connection: aiosqlite.Connection,
    session_id: str,
) -> bool:
    """``True`` if the row exists; ``False`` otherwise."""
    cursor = await connection.execute(
        "SELECT 1 FROM sessions WHERE id = ? LIMIT 1",
        (session_id,),
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    return row is not None


async def list_all(
    connection: aiosqlite.Connection,
    *,
    kind: str | None = None,
    include_closed: bool = True,
    tag_ids: tuple[int, ...] | None = None,
    tag_ids_project: tuple[int, ...] | None = None,
    tag_ids_severity: tuple[int, ...] | None = None,
    tag_ids_other: tuple[int, ...] | None = None,
    severity_none: bool = False,
) -> list[Session]:
    """Every session row matching the filters; newest-first.

    Two filter shapes: ``tag_ids`` (legacy flat OR) and the three-section
    faceted filter (``tag_ids_project`` / ``tag_ids_severity`` / ``tag_ids_other``).
    Both can be combined.  ``severity_none=True`` adds the "No severity" synthetic
    filter (gap-cycle-18-003).
    """
    _validate_list_all_args(kind, tag_ids)
    join, where, args = _build_filter_sql(
        kind,
        include_closed,
        tag_ids,
        tag_ids_project,
        tag_ids_severity,
        tag_ids_other,
        severity_none,
    )
    select = _SELECT_SESSION_COLUMNS_DISTINCT if tag_ids is not None else _SELECT_SESSION_COLUMNS
    cursor = await connection.execute(
        select + join + where + " ORDER BY sessions.updated_at DESC, sessions.id ASC",
        args,
    )
    try:
        rows = await cursor.fetchall()
    finally:
        await cursor.close()
    return [_row_to_session(row) for row in rows]


async def list_paged(
    connection: aiosqlite.Connection,
    *,
    kind: str | None = None,
    include_closed: bool = True,
    tag_ids: tuple[int, ...] | None = None,
    tag_ids_project: tuple[int, ...] | None = None,
    tag_ids_severity: tuple[int, ...] | None = None,
    tag_ids_other: tuple[int, ...] | None = None,
    severity_none: bool = False,
    limit: int = SESSIONS_MAX_PAGE_SIZE,
    offset: int = 0,
) -> tuple[list[Session], int]:
    """Return one page of sessions plus the unfiltered total count.

    Returns ``(page_rows, total)`` where ``total`` is the count of ALL rows
    matching the filter.  Two SQL round-trips: COUNT(*) first, then paginated
    SELECT.  Both share :func:`_build_filter_sql` to prevent filter drift.
    """
    _validate_list_all_args(kind, tag_ids)
    join, where, args = _build_filter_sql(
        kind,
        include_closed,
        tag_ids,
        tag_ids_project,
        tag_ids_severity,
        tag_ids_other,
        severity_none,
    )
    distinct = "DISTINCT sessions.id" if tag_ids is not None else "sessions.id"
    count_sql = f"SELECT COUNT(*) FROM (SELECT {distinct} FROM sessions{join}{where})"
    cursor = await connection.execute(count_sql, args)
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    total = int(str(row[0])) if row is not None else 0
    select = _SELECT_SESSION_COLUMNS_DISTINCT if tag_ids is not None else _SELECT_SESSION_COLUMNS
    data_sql = (
        select
        + join
        + where
        + " ORDER BY sessions.updated_at DESC, sessions.id ASC"
        + " LIMIT ? OFFSET ?"
    )
    cursor = await connection.execute(data_sql, [*args, limit, offset])
    try:
        rows = await cursor.fetchall()
    finally:
        await cursor.close()
    return [_row_to_session(r) for r in rows], total
