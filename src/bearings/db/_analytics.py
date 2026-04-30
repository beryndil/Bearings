"""Analytics aggregations for the v1.0.0 dashboard's `/analytics` page.

A single function — `get_analytics_summary` — bundles every cross-
session rollup the page renders, in one round-trip per page load.
The page is at-rest read-only, so a periodic snapshot is the right
shape; per-component fan-out would just multiply the same SQL
across N HTTP calls without changing the freshness story.

Window scoping: `days` parameter clamps the time-series queries
(sessions-by-day) to the last N days, defaulting to 30. The
totals (sessions / tokens / cost) are NOT windowed — they're
all-time, matching what a "lifetime" stat card should show.
"""

from __future__ import annotations

from typing import Any

import aiosqlite


async def get_analytics_summary(
    conn: aiosqlite.Connection, days: int = 30
) -> dict[str, Any]:
    """Aggregate every metric the analytics page renders.

    Returns a dict with the following keys:

      total_sessions, open_sessions, closed_sessions
      total_messages
      total_input_tokens, total_output_tokens,
      total_cache_read_tokens, total_cache_creation_tokens
      total_tokens         — sum of the four above
      total_cost_usd
      sessions_by_day      — list of {day: 'YYYY-MM-DD', count: int}
                             padded to `days` entries (zero-fill empty days)
      top_tags             — top 10 tags by session_count, each
                             {id, name, color, session_count}

    All counts are non-negative ints; `total_cost_usd` is a float.
    Every aggregate uses `COALESCE(SUM(...), 0)` so an empty
    database returns zeros rather than nulls.
    """
    # --- session counts -------------------------------------------------
    async with conn.execute(
        "SELECT "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) AS open_count, "
        "SUM(CASE WHEN closed_at IS NOT NULL THEN 1 ELSE 0 END) AS closed_count, "
        "COALESCE(SUM(total_cost_usd), 0.0) AS total_cost "
        "FROM sessions"
    ) as cursor:
        sess_row = await cursor.fetchone()

    total_sessions = int(sess_row["total"]) if sess_row else 0
    open_sessions = int(sess_row["open_count"] or 0) if sess_row else 0
    closed_sessions = int(sess_row["closed_count"] or 0) if sess_row else 0
    total_cost_usd = float(sess_row["total_cost"]) if sess_row else 0.0

    # --- message + token totals ----------------------------------------
    async with conn.execute(
        "SELECT "
        "COUNT(*) AS message_count, "
        "COALESCE(SUM(input_tokens), 0) AS in_tokens, "
        "COALESCE(SUM(output_tokens), 0) AS out_tokens, "
        "COALESCE(SUM(cache_read_tokens), 0) AS cache_read, "
        "COALESCE(SUM(cache_creation_tokens), 0) AS cache_creation "
        "FROM messages"
    ) as cursor:
        msg_row = await cursor.fetchone()

    total_messages = int(msg_row["message_count"]) if msg_row else 0
    total_input_tokens = int(msg_row["in_tokens"]) if msg_row else 0
    total_output_tokens = int(msg_row["out_tokens"]) if msg_row else 0
    total_cache_read = int(msg_row["cache_read"]) if msg_row else 0
    total_cache_creation = int(msg_row["cache_creation"]) if msg_row else 0
    total_tokens = (
        total_input_tokens + total_output_tokens + total_cache_read + total_cache_creation
    )

    # --- sessions by day (last `days` days) -----------------------------
    # SQLite's DATE() function strips the time component from an ISO
    # timestamp. The window predicate uses datetime('now', '-N days')
    # so the comparison stays in SQLite's UTC clock — wall-clock skew
    # between client and server is irrelevant.
    safe_days = max(1, min(days, 365))
    async with conn.execute(
        "SELECT DATE(created_at) AS day, COUNT(*) AS count "
        "FROM sessions "
        "WHERE created_at >= datetime('now', ? || ' days') "
        "GROUP BY DATE(created_at) "
        "ORDER BY day",
        (f"-{safe_days}",),
    ) as cursor:
        raw_by_day = {row["day"]: int(row["count"]) async for row in cursor}

    # Zero-fill so the front-end gets a complete `days`-long sequence —
    # rendering a sparse list of buckets makes the bar chart misleading
    # (a missing day reads as "no data" rather than "0 sessions"). The
    # bucket day strings are computed in SQLite to keep the timezone
    # decision in one place.
    async with conn.execute(
        "WITH RECURSIVE days(d) AS ("
        "SELECT DATE(datetime('now', ? || ' days')) "
        "UNION ALL "
        "SELECT DATE(d, '+1 day') FROM days WHERE d < DATE('now')"
        ") SELECT d AS day FROM days",
        (f"-{safe_days - 1}",),
    ) as cursor:
        all_days = [row["day"] async for row in cursor]

    sessions_by_day = [{"day": d, "count": raw_by_day.get(d, 0)} for d in all_days]

    # --- top tags by session count -------------------------------------
    async with conn.execute(
        "SELECT t.id, t.name, t.color, COUNT(st.session_id) AS session_count "
        "FROM tags t "
        "LEFT JOIN session_tags st ON t.id = st.tag_id "
        "GROUP BY t.id "
        "ORDER BY session_count DESC, t.name "
        "LIMIT 10"
    ) as cursor:
        top_tags = [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "color": row["color"],
                "session_count": int(row["session_count"]),
            }
            async for row in cursor
        ]

    return {
        "total_sessions": total_sessions,
        "open_sessions": open_sessions,
        "closed_sessions": closed_sessions,
        "total_messages": total_messages,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cache_read_tokens": total_cache_read,
        "total_cache_creation_tokens": total_cache_creation,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost_usd,
        "sessions_by_day": sessions_by_day,
        "top_tags": top_tags,
    }
