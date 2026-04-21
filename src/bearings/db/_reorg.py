"""Cross-session reorg helpers — move rows between `sessions`.

Slice 1 of the Session Reorg plan
(`~/.claude/plans/sparkling-triaging-otter.md`). Single primitive
`move_messages_tx` that the eventual `/api/sessions/{id}/reorg/*`
routes (move / split / merge / archive) are all composed from.
`sessions.message_count` is derived via `SELECT COUNT(*)` in
`_sessions.SESSION_COUNT`, so nothing in here has to recompute it —
touching `messages.session_id` is enough for the next read to see the
new counts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import aiosqlite

from bearings.db._common import _now


@dataclass(frozen=True)
class MoveResult:
    """Counts returned by `move_messages_tx`.

    `moved` counts messages whose `session_id` actually changed; rows
    already on the target (from a prior call) are excluded because the
    primitive is idempotent. `tool_calls_followed` counts `tool_calls`
    rows updated because they were anchored (via `message_id`) to a
    moved message. Orphan tool calls (null `message_id`) stay with the
    source session.
    """

    moved: int
    tool_calls_followed: int


async def move_messages_tx(
    conn: aiosqlite.Connection,
    *,
    source_id: str,
    target_id: str,
    message_ids: Sequence[str],
) -> MoveResult:
    """Atomically move `message_ids` from source to target session.

    Behavior:
    - Idempotent. The `session_id = source_id` guard means a second
      call on the same ids returns `moved=0` without error.
    - Partial input is tolerated. Ids absent from the source are
      silently skipped; they don't count toward `moved`.
    - Tool calls anchored to moved messages follow their message to
      the target. Orphan tool calls stay behind.
    - Both sessions' `updated_at` bump iff at least one message moved,
      so the sidebar re-sorts on next `list_sessions`.
    - `sessions.message_count` is a derived SELECT, so no recompute.

    Raises:
        ValueError: if `source_id == target_id` or the target session
            does not exist. A missing source is tolerated and yields a
            no-op result (nothing matches the guard).

    Rolls back on any mid-operation exception; `conn.commit()` runs
    exactly once on the happy path.
    """
    if source_id == target_id:
        raise ValueError("source and target sessions must differ")
    if not message_ids:
        return MoveResult(moved=0, tool_calls_followed=0)

    async with conn.execute("SELECT 1 FROM sessions WHERE id = ?", (target_id,)) as cursor:
        if await cursor.fetchone() is None:
            raise ValueError(f"target session {target_id!r} does not exist")

    placeholders = ",".join("?" for _ in message_ids)
    now = _now()

    try:
        msg_cursor = await conn.execute(
            f"UPDATE messages SET session_id = ? WHERE session_id = ? AND id IN ({placeholders})",
            (target_id, source_id, *message_ids),
        )
        moved = msg_cursor.rowcount

        tc_cursor = await conn.execute(
            f"UPDATE tool_calls SET session_id = ? "
            f"WHERE session_id = ? AND message_id IN ({placeholders})",
            (target_id, source_id, *message_ids),
        )
        tool_calls_followed = tc_cursor.rowcount

        if moved > 0:
            await conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id IN (?, ?)",
                (now, source_id, target_id),
            )

        await conn.commit()
    except BaseException:
        await conn.rollback()
        raise

    return MoveResult(moved=moved, tool_calls_followed=tool_calls_followed)
