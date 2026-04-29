"""``messages`` table queries — chat-kind transcript rows.

Per ``docs/architecture-v1.md`` §1.1.3 this concern module owns every
query that touches ``messages``. Per ``docs/model-routing-v1-spec.md``
§5 the table carries per-model routing/usage columns from day 1
(see ``schema.sql`` — ``executor_model`` / ``advisor_model`` /
``effort_level`` / ``routing_source`` / ``routing_reason`` plus the
five usage columns); item 1.7 lays the user-message INSERT path that
the prompt endpoint uses, leaving the assistant-turn persistence for
item 1.2/1.3's streaming integration.

Public surface (item-1.7 narrow slice):

* :class:`Message` — frozen dataclass row mirror with
  ``__post_init__`` validation.
* :func:`insert_user`, :func:`insert_system` — non-routing rows
  (``role='user'`` / ``'system'``); the routing/usage columns stay
  NULL and are filled at assistant-turn persist time.
* :func:`get`, :func:`list_for_session`, :func:`count_for_session` —
  read paths the WS handler + the prompt endpoint use.
* :func:`bump_session_message_count` — increment ``sessions.message_count``
  in lockstep with a row insert. Internal helper but exposed so the
  prompt endpoint can call it inside the same transaction the user-row
  insert uses.

Per ``docs/behavior/prompt-endpoint.md`` §"Observability of the queued
prompt" — "The user message is durably persisted **before** the runner
begins the turn." That guarantees a 202 ack survives a server crash
between accept and turn-start; the prompt is replayed on next boot.
"""

from __future__ import annotations

from dataclasses import dataclass

import aiosqlite

from bearings.config.constants import MESSAGE_ID_PREFIX
from bearings.db._id import new_id, now_iso

# Roles the schema accepts (CHECK constraint mirror).
KNOWN_MESSAGE_ROLES: frozenset[str] = frozenset({"user", "assistant", "system", "tool"})


@dataclass(frozen=True)
class Message:
    """Row mirror for the ``messages`` table.

    The routing/usage columns are nullable — only assistant rows
    (filled by the per-turn persistence path, item 1.2+/1.3+) carry
    them. User rows leave them ``None``, which the analytics queries
    filter out via ``routing_source IS NULL``.
    """

    id: str
    session_id: str
    role: str
    content: str
    created_at: str
    executor_model: str | None
    advisor_model: str | None
    effort_level: str | None
    routing_source: str | None
    routing_reason: str | None
    executor_input_tokens: int | None
    executor_output_tokens: int | None
    advisor_input_tokens: int | None
    advisor_output_tokens: int | None
    advisor_calls_count: int | None
    cache_read_tokens: int | None
    input_tokens: int | None
    output_tokens: int | None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Message.id must be non-empty")
        if not self.session_id:
            raise ValueError("Message.session_id must be non-empty")
        if self.role not in KNOWN_MESSAGE_ROLES:
            raise ValueError(f"Message.role {self.role!r} not in {sorted(KNOWN_MESSAGE_ROLES)}")
        # Empty content is allowed for tool rows (a tool that produced no
        # stdout); user rows are validated at the API boundary against
        # the prompt-endpoint's "non-empty after stripping whitespace"
        # rule, so this dataclass does not gate on user-row content.


async def insert_user(
    connection: aiosqlite.Connection,
    *,
    session_id: str,
    content: str,
) -> Message:
    """Insert a user-role message row + bump ``sessions.message_count``.

    The two writes happen inside one transaction (a single ``commit``
    after both UPDATEs) so the count never lies relative to the row.
    Per ``docs/behavior/prompt-endpoint.md`` §"Observability of the
    queued prompt" the row must be durable before the runner picks up
    the prompt — the caller is responsible for not dispatching to the
    runner until this returns.
    """
    return await _insert(connection, session_id=session_id, role="user", content=content)


async def insert_system(
    connection: aiosqlite.Connection,
    *,
    session_id: str,
    content: str,
) -> Message:
    """Insert a system-role message row.

    System rows are how Bearings surfaces session-state notices the
    user observes inline (e.g. the "resuming prompt from previous
    session" hint per behavior doc §"Observability of the queued
    prompt"). Same write-then-bump shape as :func:`insert_user`.
    """
    return await _insert(connection, session_id=session_id, role="system", content=content)


async def _insert(
    connection: aiosqlite.Connection,
    *,
    session_id: str,
    role: str,
    content: str,
) -> Message:
    """Internal — insert a non-routing row and bump the session counter."""
    timestamp = now_iso()
    message_id = new_id(MESSAGE_ID_PREFIX)
    Message(
        id=message_id,
        session_id=session_id,
        role=role,
        content=content,
        created_at=timestamp,
        executor_model=None,
        advisor_model=None,
        effort_level=None,
        routing_source=None,
        routing_reason=None,
        executor_input_tokens=None,
        executor_output_tokens=None,
        advisor_input_tokens=None,
        advisor_output_tokens=None,
        advisor_calls_count=None,
        cache_read_tokens=None,
        input_tokens=None,
        output_tokens=None,
    )
    await connection.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (message_id, session_id, role, content, timestamp),
    )
    await connection.execute(
        "UPDATE sessions SET message_count = message_count + 1, updated_at = ? WHERE id = ?",
        (timestamp, session_id),
    )
    await connection.commit()
    fetched = await get(connection, message_id)
    if fetched is None:  # pragma: no cover — INSERT just succeeded
        raise RuntimeError(f"messages._insert: row {message_id!r} vanished after INSERT")
    return fetched


async def get(
    connection: aiosqlite.Connection,
    message_id: str,
) -> Message | None:
    """Fetch a single message by id; ``None`` if absent."""
    cursor = await connection.execute(
        _SELECT_MESSAGE_COLUMNS + " WHERE id = ?",
        (message_id,),
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    return None if row is None else _row_to_message(row)


async def list_for_session(
    connection: aiosqlite.Connection,
    session_id: str,
    *,
    limit: int | None = None,
) -> list[Message]:
    """Every message under ``session_id``, oldest-first.

    Optional ``limit`` returns the **last** N rows (most recent N) —
    used by the WS reconnect path which only needs the tail of the
    transcript on first paint.
    """
    if limit is not None and limit <= 0:
        raise ValueError(f"list_for_session: limit must be > 0 if set (got {limit})")
    if limit is None:
        cursor = await connection.execute(
            _SELECT_MESSAGE_COLUMNS + " WHERE session_id = ? ORDER BY created_at ASC, id ASC",
            (session_id,),
        )
    else:
        # Last N — order by created_at DESC, take limit, then reverse
        # for chronological order at the call site.
        cursor = await connection.execute(
            _SELECT_MESSAGE_COLUMNS + " WHERE session_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (session_id, limit),
        )
    try:
        rows = await cursor.fetchall()
    finally:
        await cursor.close()
    messages = [_row_to_message(row) for row in rows]
    if limit is not None:
        messages.reverse()
    return messages


async def count_for_session(
    connection: aiosqlite.Connection,
    session_id: str,
) -> int:
    """Number of messages on ``session_id``."""
    cursor = await connection.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id = ?",
        (session_id,),
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    return 0 if row is None else int(row[0])


_SELECT_MESSAGE_COLUMNS = (
    "SELECT id, session_id, role, content, created_at, "
    "executor_model, advisor_model, effort_level, routing_source, routing_reason, "
    "executor_input_tokens, executor_output_tokens, advisor_input_tokens, "
    "advisor_output_tokens, advisor_calls_count, cache_read_tokens, "
    "input_tokens, output_tokens FROM messages"
)


def _row_to_message(row: aiosqlite.Row | tuple[object, ...]) -> Message:
    """Translate a raw SELECT tuple into a validated :class:`Message`."""
    return Message(
        id=str(row[0]),
        session_id=str(row[1]),
        role=str(row[2]),
        content=str(row[3]),
        created_at=str(row[4]),
        executor_model=None if row[5] is None else str(row[5]),
        advisor_model=None if row[6] is None else str(row[6]),
        effort_level=None if row[7] is None else str(row[7]),
        routing_source=None if row[8] is None else str(row[8]),
        routing_reason=None if row[9] is None else str(row[9]),
        executor_input_tokens=None if row[10] is None else int(str(row[10])),
        executor_output_tokens=None if row[11] is None else int(str(row[11])),
        advisor_input_tokens=None if row[12] is None else int(str(row[12])),
        advisor_output_tokens=None if row[13] is None else int(str(row[13])),
        advisor_calls_count=None if row[14] is None else int(str(row[14])),
        cache_read_tokens=None if row[15] is None else int(str(row[15])),
        input_tokens=None if row[16] is None else int(str(row[16])),
        output_tokens=None if row[17] is None else int(str(row[17])),
    )


__all__ = [
    "KNOWN_MESSAGE_ROLES",
    "Message",
    "count_for_session",
    "get",
    "insert_system",
    "insert_user",
    "list_for_session",
]
