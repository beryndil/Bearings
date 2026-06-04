"""Aggregate-view routes — viewed, paired-chat, tool_calls, todos, system_prompt, tokens.

These endpoints return derived or assembled data about a session rather than
mutating it.  Export/import and work-evidence live in ``sessions_io``.
"""

from __future__ import annotations

import json as _json
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from bearings.agent.prompt_assembler import assemble_system_prompt_layers
from bearings.db import messages as messages_db
from bearings.db import sessions as sessions_db
from bearings.db import tool_calls as tool_calls_db
from bearings.web.models.errors import DetailError
from bearings.web.models.sessions import (
    PairedChatInfo,
    SessionOut,
    SessionTodosOut,
    SystemPromptLayerOut,
    SystemPromptLayersOut,
    TokenTotalsOut,
    ToolCallOut,
)
from bearings.web.routes._sessions_helpers import (
    _db,
    _fetch_tags_out,
    _sessions_broadcaster,
    _to_out,
)

router = APIRouter()
_log = logging.getLogger(__name__)


# ---- viewed ----------------------------------------------------------------


@router.post(
    "/api/sessions/{session_id}/viewed",
    response_model=SessionOut,
    operation_id="mark-session-viewed",
)
async def update_session_viewed(session_id: str, request: Request) -> SessionOut:
    """Stamp ``last_viewed_at`` to now; broadcast the upsert.

    Clears the unviewed amber dot on every other open tab within one WS tick.
    404 when the session is absent.
    """
    db = _db(request)
    row = await sessions_db.mark_viewed(db, session_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    tags = await _fetch_tags_out(db, session_id)
    out = _to_out(row, tags=tags)
    broadcaster = _sessions_broadcaster(request)
    if broadcaster is not None:
        broadcaster.publish_upsert(out)
    return out


# ---- paired-chat info ------------------------------------------------------


@router.get(
    "/api/sessions/{session_id}/paired-chat-info",
    operation_id="get-session-paired-chat-info",
    responses={404: {"model": DetailError, "description": "Session not found."}},
)
async def get_paired_chat_info_route(session_id: str, request: Request) -> PairedChatInfo | None:
    """Fetch paired-chat metadata (parent title + item label) for a chat session.

    Per ``docs/behavior/paired-chats.md`` §"From the chat side".
    Returns ``null`` when the session is unpaired; 404 when the session is absent.
    """
    db = _db(request)
    row = await sessions_db.get(db, session_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    info = await sessions_db.get_paired_chat_info(db, session_id)
    if info is None:
        return None
    parent_title, item_label = info
    return PairedChatInfo(parent_title=parent_title, item_label=item_label)


# ---- tool calls (gap-cycle-03-012) -----------------------------------------


@router.get(
    "/api/sessions/{session_id}/tool_calls",
    response_model=list[ToolCallOut],
    operation_id="list-session-tool-calls",
)
async def list_session_tool_calls(
    session_id: str,
    request: Request,
    message_ids: Annotated[list[str] | None, Query()] = None,
) -> list[ToolCallOut]:
    """Return persisted tool-call rows for the listed message ids.

    Per ``docs/behavior/chat.md`` §"Tool-call hydration contract".
    Omitting ``message_ids`` returns all tool calls for the session.
    """
    db = _db(request)
    if not await sessions_db.exists(db, session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    ids = list(message_ids) if message_ids else []
    if not ids:
        cursor = await db.execute(
            "SELECT id, session_id, message_id, tool_name, input_json, "
            "       output, ok, duration_ms, error_message, created_at "
            "FROM tool_calls WHERE session_id = ? ORDER BY rowid ASC",
            (session_id,),
        )
        try:
            rows = await cursor.fetchall()
        finally:
            await cursor.close()
        return [
            ToolCallOut(
                id=str(r[0]),
                session_id=str(r[1]),
                message_id=str(r[2]),
                tool_name=str(r[3]),
                input_json=str(r[4]),
                output=str(r[5]),
                ok=(bool(int(str(r[6]))) if r[6] is not None else None),
                duration_ms=(int(str(r[7])) if r[7] is not None else None),
                error_message=(str(r[8]) if r[8] is not None else None),
                created_at=str(r[9]),
            )
            for r in rows
        ]
    tc_rows = await tool_calls_db.list_for_messages(db, session_id=session_id, message_ids=ids)
    return [
        ToolCallOut(
            id=tc.id,
            session_id=tc.session_id,
            message_id=tc.message_id,
            tool_name=tc.tool_name,
            input_json=tc.input_json,
            output=tc.output,
            ok=tc.ok,
            duration_ms=tc.duration_ms,
            error_message=tc.error_message,
            created_at=tc.created_at,
        )
        for tc in tc_rows
    ]


# ---- todos hydration (gap-cycle-03-013) ------------------------------------


@router.get(
    "/api/sessions/{session_id}/todos",
    response_model=SessionTodosOut | None,
    operation_id="get-session-todos",
)
async def get_session_todos(session_id: str, request: Request) -> SessionTodosOut | None:
    """Return the most-recent persisted ``TodoWrite`` payload for a session.

    Per ``docs/behavior/chat.md`` §"LiveTodos hydration contract".
    Returns ``null`` (200) when the session exists but has never emitted
    a ``TodoWrite`` call; 404 when the session is absent.
    """
    db = _db(request)
    if not await sessions_db.exists(db, session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    input_json = await tool_calls_db.latest_todo_write_json(db, session_id=session_id)
    if input_json is None:
        return None
    try:
        parsed = _json.loads(input_json)
        todos = parsed.get("todos", [])
        todos_json = _json.dumps(todos)
    except (ValueError, AttributeError):
        todos_json = "[]"
    return SessionTodosOut(todos_json=todos_json)


# ---- system-prompt layer breakdown (gap-cycle-13-004) ----------------------


@router.get(
    "/api/sessions/{session_id}/system_prompt",
    response_model=SystemPromptLayersOut,
    operation_id="get-session-system-prompt",
)
async def get_session_system_prompt(session_id: str, request: Request) -> SystemPromptLayersOut:
    """Return the assembled system-prompt layer breakdown for a session.

    Per ``docs/behavior/chat.md`` §"System-prompt layers contract"
    (gap-cycle-13-004).  404 when the session is absent.
    """
    db = _db(request)
    result = await assemble_system_prompt_layers(db, session_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    return SystemPromptLayersOut(
        layers=[
            SystemPromptLayerOut(
                kind=layer.kind,
                body=layer.body,
                token_count=layer.token_count,
                source_path=layer.source_path,
            )
            for layer in result.layers
        ],
        total_tokens=result.total_tokens,
        token_count_approximate=True,
    )


# ---- token totals hydration (gap-cycle-13-003) -----------------------------


@router.get(
    "/api/sessions/{session_id}/tokens",
    response_model=TokenTotalsOut,
    operation_id="get-session-tokens",
)
async def get_session_tokens(session_id: str, request: Request) -> TokenTotalsOut:
    """Return aggregated lifetime token totals for a session.

    Per ``docs/behavior/chat.md`` §"Token totals hydration contract"
    (gap-cycle-13-003).  Returns ``0`` for all fields when no assistant
    turns exist yet.  404 when the session is absent.
    """
    db = _db(request)
    if not await sessions_db.exists(db, session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    inp, out, cache_read, cache_creation = await messages_db.get_token_totals(db, session_id)
    return TokenTotalsOut(
        input=inp,
        output=out,
        cache_read=cache_read,
        cache_creation=cache_creation,
    )
