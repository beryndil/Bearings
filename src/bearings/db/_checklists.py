"""Checklists + checklist_items. A checklist is a 1:1 companion to
`sessions` rows whose `kind = 'checklist'` — the session row carries
the title, tags, and lifecycle flags; the checklist row carries the
structured body (notes + items). The runner never attaches to a
checklist session; these helpers are the entire mutation surface.

Public functions mirror the shape of `_tags.py`: each returns a
refreshed dict row or `None` when the target is missing. Timestamps
are ISO via `_common._now()` to match every other column. A
single-round-trip `get_checklist` includes the item list so the UI
can paint on one response rather than stitching two.
"""

from __future__ import annotations

from typing import Any

import aiosqlite

from bearings.db._common import _now

CHECKLIST_COLS = "session_id, notes, created_at, updated_at"
ITEM_COLS = (
    "id, checklist_id, parent_item_id, label, notes, checked_at, sort_order, created_at, updated_at"
)
# Top-level items ordered by sort_order then id; nested children
# follow the same rule under their parent (resolved client-side for
# now — a single flat list is cheaper to ship than a recursive CTE
# and the nesting UI lands in a later slice anyway).
ITEM_ORDER = "sort_order ASC, id ASC"


async def create_checklist(
    conn: aiosqlite.Connection,
    session_id: str,
    *,
    notes: str | None = None,
) -> dict[str, Any]:
    """Insert the 1:1 checklist row for `session_id`. Caller is
    responsible for ensuring the session row exists and carries
    `kind = 'checklist'` — this helper doesn't validate the parent
    because the normal creation path is the `POST /sessions` handler
    doing both inserts inside one transaction."""
    now = _now()
    await conn.execute(
        "INSERT INTO checklists (session_id, notes, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (session_id, notes, now, now),
    )
    await conn.commit()
    row = await get_checklist(conn, session_id)
    assert row is not None  # just inserted
    return row


async def get_checklist(conn: aiosqlite.Connection, session_id: str) -> dict[str, Any] | None:
    """Return the checklist row for `session_id` with its items inline,
    or `None` when the row doesn't exist. Items come back flat in
    sort_order then id; nesting is recovered client-side via
    `parent_item_id`."""
    async with conn.execute(
        f"SELECT {CHECKLIST_COLS} FROM checklists WHERE session_id = ?",
        (session_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    out = dict(row)
    async with conn.execute(
        f"SELECT {ITEM_COLS} FROM checklist_items WHERE checklist_id = ? ORDER BY {ITEM_ORDER}",
        (session_id,),
    ) as cursor:
        out["items"] = [dict(r) async for r in cursor]
    return out


async def update_checklist(
    conn: aiosqlite.Connection,
    session_id: str,
    *,
    fields: dict[str, Any],
) -> dict[str, Any] | None:
    """Partial update. `fields` may carry `notes`; unknown keys are
    ignored so the HTTP layer can pass a permissive dict. Bumps
    `updated_at`. Returns the refreshed row (with items) or `None`
    when the checklist doesn't exist."""
    allowed = {"notes"}
    filtered = {k: v for k, v in fields.items() if k in allowed}
    if not filtered:
        return await get_checklist(conn, session_id)
    assignments = ", ".join(f"{col} = ?" for col in filtered)
    params = (*filtered.values(), _now(), session_id)
    cursor = await conn.execute(
        f"UPDATE checklists SET {assignments}, updated_at = ? WHERE session_id = ?",
        params,
    )
    await conn.commit()
    if cursor.rowcount == 0:
        return None
    return await get_checklist(conn, session_id)


async def get_item(conn: aiosqlite.Connection, item_id: int) -> dict[str, Any] | None:
    async with conn.execute(
        f"SELECT {ITEM_COLS} FROM checklist_items WHERE id = ?",
        (item_id,),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row is not None else None


async def create_item(
    conn: aiosqlite.Connection,
    checklist_id: str,
    *,
    label: str,
    notes: str | None = None,
    parent_item_id: int | None = None,
    sort_order: int | None = None,
) -> dict[str, Any] | None:
    """Insert a new item. When `sort_order` is omitted, we append —
    `MAX(sort_order) + 1` among siblings so the new row lands at the
    bottom of its sibling list. Returns `None` if the parent
    checklist doesn't exist (FK would fail); otherwise the freshly
    inserted row."""
    parent_check = await conn.execute(
        "SELECT 1 FROM checklists WHERE session_id = ?", (checklist_id,)
    )
    if await parent_check.fetchone() is None:
        return None
    if sort_order is None:
        async with conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM checklist_items "
            "WHERE checklist_id = ? AND "
            "(parent_item_id IS ? OR parent_item_id = ?)",
            (checklist_id, parent_item_id, parent_item_id),
        ) as cursor:
            max_row = await cursor.fetchone()
            sort_order = int(max_row[0]) if max_row is not None else 0
    now = _now()
    cursor = await conn.execute(
        "INSERT INTO checklist_items "
        "(checklist_id, parent_item_id, label, notes, sort_order, "
        "created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (checklist_id, parent_item_id, label, notes, sort_order, now, now),
    )
    # Touch the parent checklist so `updated_at` reflects the latest
    # mutation — mirrors how `insert_message` bumps the session row.
    await conn.execute(
        "UPDATE checklists SET updated_at = ? WHERE session_id = ?",
        (now, checklist_id),
    )
    await conn.commit()
    item_id = cursor.lastrowid
    assert item_id is not None
    inserted = await get_item(conn, item_id)
    assert inserted is not None
    return inserted


async def update_item(
    conn: aiosqlite.Connection,
    item_id: int,
    *,
    fields: dict[str, Any],
) -> dict[str, Any] | None:
    """Partial update. Accepts `label`, `notes`, `parent_item_id`,
    `sort_order`. Bumps `updated_at` on both the item and its parent
    checklist. Returns `None` if the item id is unknown."""
    allowed = {"label", "notes", "parent_item_id", "sort_order"}
    filtered = {k: v for k, v in fields.items() if k in allowed}
    if not filtered:
        return await get_item(conn, item_id)
    assignments = ", ".join(f"{col} = ?" for col in filtered)
    now = _now()
    params = (*filtered.values(), now, item_id)
    cursor = await conn.execute(
        f"UPDATE checklist_items SET {assignments}, updated_at = ? WHERE id = ?",
        params,
    )
    if cursor.rowcount == 0:
        await conn.commit()
        return None
    # Bump the parent checklist too — cheap JOIN to recover the id.
    await conn.execute(
        "UPDATE checklists SET updated_at = ? WHERE session_id = "
        "(SELECT checklist_id FROM checklist_items WHERE id = ?)",
        (now, item_id),
    )
    await conn.commit()
    return await get_item(conn, item_id)


async def toggle_item(
    conn: aiosqlite.Connection, item_id: int, *, checked: bool
) -> dict[str, Any] | None:
    """Set or clear `checked_at`. Passing `checked=True` stamps the
    current time; `checked=False` clears the column. No-op if the
    item is already in the requested state — but `updated_at` is
    still bumped so the UI can sort by recency."""
    now = _now()
    checked_at = now if checked else None
    cursor = await conn.execute(
        "UPDATE checklist_items SET checked_at = ?, updated_at = ? WHERE id = ?",
        (checked_at, now, item_id),
    )
    if cursor.rowcount == 0:
        await conn.commit()
        return None
    await conn.execute(
        "UPDATE checklists SET updated_at = ? WHERE session_id = "
        "(SELECT checklist_id FROM checklist_items WHERE id = ?)",
        (now, item_id),
    )
    await conn.commit()
    return await get_item(conn, item_id)


async def delete_item(conn: aiosqlite.Connection, item_id: int) -> bool:
    """Delete an item. Cascade-on-delete sweeps any nested children
    the same way. Returns True if a row was removed."""
    # Capture the parent checklist id so we can bump its updated_at
    # after the delete commits.
    parent_row = await conn.execute(
        "SELECT checklist_id FROM checklist_items WHERE id = ?", (item_id,)
    )
    parent = await parent_row.fetchone()
    cursor = await conn.execute("DELETE FROM checklist_items WHERE id = ?", (item_id,))
    deleted = cursor.rowcount > 0
    if deleted and parent is not None:
        await conn.execute(
            "UPDATE checklists SET updated_at = ? WHERE session_id = ?",
            (_now(), parent["checklist_id"]),
        )
    await conn.commit()
    return deleted


async def reorder_items(
    conn: aiosqlite.Connection,
    checklist_id: str,
    ordered_ids: list[int],
) -> int:
    """Bulk sort_order rewrite. Items not in `ordered_ids` keep their
    existing `sort_order`. Foreign items (ids belonging to another
    checklist) are silently skipped so a malicious client can't
    reorder a list it doesn't own. Returns the number of rows
    actually rewritten."""
    if not ordered_ids:
        return 0
    now = _now()
    written = 0
    for i, item_id in enumerate(ordered_ids):
        cursor = await conn.execute(
            "UPDATE checklist_items SET sort_order = ?, updated_at = ? "
            "WHERE id = ? AND checklist_id = ?",
            (i, now, item_id, checklist_id),
        )
        written += cursor.rowcount
    if written > 0:
        await conn.execute(
            "UPDATE checklists SET updated_at = ? WHERE session_id = ?",
            (now, checklist_id),
        )
    await conn.commit()
    return written
