"""Assistant-turn DB persistence for `SessionRunner`.

`persist_assistant_turn` lands the streamed assistant message body
(plus optional thinking trace), attaches its tool calls, accrues the
session cost, and stamps `last_completed_at` for the sidebar's amber
"finished but unviewed" dot. Lives outside `runner.py` so the runner
keeps its own surface focused on the worker loop and stream fan-out.

Called from both the normal `MessageComplete` arm of `_execute_turn`
and the stop-requested synthetic-completion path. The runner is the
sole caller — public name (no underscore prefix) just because it now
crosses a module boundary.

All four writes (message insert, tool-call backfill, cost accrual,
session completion stamp) execute under one deferred transaction and
land via a single `conn.commit()` at the end. Pre-L3.1 each helper
committed independently, so a reader polling `tool_calls` could
observe the freshly-inserted assistant row before the FK backfill
landed (the race documented in `tests/test_routes_sessions.py:480`).
The single-commit shape closes that race AND drops the per-turn fsync
count by 4 — matching the reduction the L3.1 punch-list item targets.
The `move_messages_tx` helper in `bearings.db._reorg` is the
canonical model for this shape.
"""

from __future__ import annotations

import aiosqlite

from bearings import metrics
from bearings.db import store


async def persist_assistant_turn(
    conn: aiosqlite.Connection,
    *,
    session_id: str,
    message_id: str,
    content: str,
    thinking: str | None,
    tool_call_ids: list[str],
    cost_usd: float | None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    cache_creation_tokens: int | None = None,
) -> None:
    try:
        await store.insert_message(
            conn,
            session_id=session_id,
            id=message_id,
            role="assistant",
            content=content,
            thinking=thinking,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
            commit=False,
        )
        await store.attach_tool_calls_to_message(
            conn,
            message_id=message_id,
            tool_call_ids=tool_call_ids,
            commit=False,
        )
        if cost_usd is not None:
            await store.add_session_cost(conn, session_id, cost_usd, commit=False)
        # Stamp last_completed_at for the sidebar's "finished but
        # unviewed" amber dot. Runs on every assistant turn persist
        # including the stop-requested synthetic, so an interrupted
        # turn still counts as completed output for the viewer to read.
        await store.mark_session_completed(conn, session_id, commit=False)
        await conn.commit()
    except BaseException:
        await conn.rollback()
        raise
    # Counter is bumped after the commit so it reflects durably
    # persisted assistant turns rather than attempts that may have
    # rolled back on the line above.
    metrics.messages_persisted.labels(role="assistant").inc()
