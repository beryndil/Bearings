"""Prompt, stop, recover, regenerate, and suggest-title routes.

Exec-2B's 401-retry will land in the agent layer (sdk_loop_errors).  This
module owns the HTTP surface: enqueueing prompts, stopping turns, recovering
from ERROR state, and the suggest-title LLM call.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request, Response, status

from bearings.agent.prompt_dispatch import dispatch_prompt
from bearings.config.constants import (
    SUGGEST_TITLE_DEFAULT_MODEL,
    SUGGEST_TITLE_EXCERPT_MAX_CHARS,
    SUGGEST_TITLE_MESSAGE_LIMIT,
    SUGGEST_TITLE_RESPONSE_MAX_CHARS,
    SUGGEST_TITLE_TIMEOUT_S,
)
from bearings.db import messages as messages_db
from bearings.db import sessions as sessions_db
from bearings.web.models.sessions import (
    PromptAck,
    PromptIn,
    SuggestTitleOut,
)
from bearings.web.routes._sessions_helpers import (
    _db,
    _dispatch_result_to_response,
    _fetch_tags_out,
    _rate_limiter,
    _runner_factory,
    _sessions_broadcaster,
    _to_out,
)
from bearings.web.runner_factory import InProcessRunnerRegistry

router = APIRouter()
_log = logging.getLogger(__name__)


# ---- prompt endpoint -------------------------------------------------------


@router.post(
    "/api/sessions/{session_id}/prompt",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="prompt-session",
    responses={202: {"model": PromptAck}},
)
async def prompt_session(
    session_id: str,
    payload: PromptIn,
    request: Request,
) -> Response:
    """Inject a user-role prompt into a session's queue.

    Per ``docs/behavior/prompt-endpoint.md`` §"202 semantics" the success
    response is 202 Accepted with ``{queued: true, session_id: <id>}``.
    """
    db = _db(request)
    factory = _runner_factory(request)
    limiter = _rate_limiter(request)
    result = await dispatch_prompt(
        db,
        factory,
        limiter,
        session_id=session_id,
        content=payload.content,
        force_advisor=payload.force_advisor,
    )
    return _dispatch_result_to_response(result, session_id)


# ---- stop / cancel turn ----------------------------------------------------


@router.post(
    "/api/sessions/{session_id}/stop",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="stop-session-turn",
)
async def stop_session_turn(session_id: str, request: Request) -> None:
    """Ask the runner to interrupt the current in-flight turn.

    Idempotent — returns 204 even when no turn is running.  404 when
    no session row exists.  503 when the runner registry is not wired.
    """
    db = _db(request)
    if not await sessions_db.exists(db, session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    factory = getattr(request.app.state, "runner_factory", None)
    if not isinstance(factory, InProcessRunnerRegistry):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="stop requires the in-process runner registry",
        )
    runner = factory.get(session_id)
    if runner is not None:
        runner.request_stop()


# ---- recover ---------------------------------------------------------------


@router.post(
    "/api/sessions/{session_id}/recover",
    response_model=None,  # SessionOut shape but operation_id is recover
    operation_id="recover-session",
)
async def resume_session(session_id: str, request: Request) -> object:
    """User-driven recovery from ERROR state.

    Clears ``error_pending`` and triggers a runner respawn so the next
    prompt can proceed.  Per ``docs/behavior/chat.md`` §"Error states".
    """
    db = _db(request)
    row = await sessions_db.set_error_pending(db, session_id, False)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    factory = getattr(request.app.state, "runner_factory", None)
    if isinstance(factory, InProcessRunnerRegistry):
        await factory(session_id)
    tags = await _fetch_tags_out(db, session_id)
    out = _to_out(row, tags=tags)
    broadcaster = _sessions_broadcaster(request)
    if broadcaster is not None:
        broadcaster.publish_upsert(out)
    return out


# ---- regenerate ------------------------------------------------------------


@router.post(
    "/api/sessions/{session_id}/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="regenerate-session",
    responses={202: {"model": PromptAck}},
)
async def regenerate_session(session_id: str, request: Request) -> Response:
    """Re-enqueue the latest user prompt.

    404 when the session is missing or has no user messages.  409 on
    closed session.  429 on rate limit.  Returns 202 mirror of the
    prompt endpoint's ack.
    """
    db = _db(request)
    factory = _runner_factory(request)
    limiter = _rate_limiter(request)
    if not await sessions_db.exists(db, session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    content = await messages_db.latest_user_content(db, session_id)
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session {session_id!r} has no user messages to regenerate from",
        )
    result = await dispatch_prompt(db, factory, limiter, session_id=session_id, content=content)
    return _dispatch_result_to_response(result, session_id)


# ---- regenerate from pivot message -----------------------------------------


@router.post(
    "/api/sessions/{session_id}/regenerate_from/{message_id}",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="regenerate-session-from-message",
    responses={202: {"model": PromptAck}},
)
async def regenerate_from_message(
    session_id: str,
    message_id: str,
    request: Request,
) -> Response:
    """Truncate the transcript to the pivot user message and re-queue it.

    Per ``docs/behavior/chat.md`` §"Regenerate from here" (gap-cycle-03-006).
    ``message_id`` must name an assistant-role turn; the preceding user
    message becomes the re-queued content.
    """
    db = _db(request)
    factory = _runner_factory(request)
    limiter = _rate_limiter(request)
    if not await sessions_db.exists(db, session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    pivot_assistant = await messages_db.get(db, message_id)
    if pivot_assistant is None or pivot_assistant.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no message matches {message_id!r} in session {session_id!r}",
        )
    if pivot_assistant.role != "assistant":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"message {message_id!r} is not an assistant turn",
        )
    pivot_user = await messages_db.get_preceding_user_message(
        db, session_id, before_seq=pivot_assistant.seq
    )
    if pivot_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no user message precedes message {message_id!r} in session {session_id!r}",
        )
    await messages_db.truncate_after(db, session_id, pivot_seq=pivot_user.seq)
    result = await dispatch_prompt(
        db, factory, limiter, session_id=session_id, content=pivot_user.content
    )
    return _dispatch_result_to_response(result, session_id)


# ---- suggest_title (T1-03) -------------------------------------------------


async def _run_suggest_title(excerpt: str, model: str) -> str | None:
    """Spawn ``claude -p`` to suggest a session title from a conversation excerpt.

    Returns the suggested title (stripped) or ``None`` on any error.
    The subprocess is killed if it runs past :data:`SUGGEST_TITLE_TIMEOUT_S`.
    """
    prompt = (
        "Based on the conversation excerpt below, reply with a concise 3-8 word title "
        "that captures the main topic.  Reply with the title only — no quotes, no "
        "punctuation at the end, no explanation.\n\n" + excerpt
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "-p",
            prompt,
            "-m",
            model,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=SUGGEST_TITLE_TIMEOUT_S,
        )
        if proc.returncode == 0:
            raw = stdout.decode(errors="replace").strip()
            return raw[:SUGGEST_TITLE_RESPONSE_MAX_CHARS] if raw else None
        return None
    except Exception as exc:
        _log.debug("suggest_title subprocess error: %s", exc)
        return None


@router.post(
    "/api/sessions/{session_id}/preview_title",
    response_model=SuggestTitleOut,
    operation_id="preview-session-title",
)
async def preview_session_title(
    session_id: str,
    request: Request,
) -> SuggestTitleOut:
    """Preview a generated title for a session based on its conversation excerpt (T1-03).

    Fetches the last :data:`SUGGEST_TITLE_MESSAGE_LIMIT` messages and sends a
    short excerpt to the Claude CLI.  ``app.state.title_suggester`` overrides
    the subprocess call in tests.  Broadcasts ``session_upsert`` after (CCW-3).
    """
    db = _db(request)
    broadcaster = _sessions_broadcaster(request)
    row = await sessions_db.get(db, session_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    messages = await messages_db.list_for_session(db, session_id, limit=SUGGEST_TITLE_MESSAGE_LIMIT)
    if not messages:
        return SuggestTitleOut(suggested_title=None)
    lines = []
    for m in messages:
        role_label = m.role.upper()
        snippet = m.content[:500].replace("\n", " ")
        lines.append(f"{role_label}: {snippet}")
    excerpt = "\n\n".join(lines)
    excerpt = excerpt[:SUGGEST_TITLE_EXCERPT_MAX_CHARS]
    model = row.routing_advisor_model or row.model or SUGGEST_TITLE_DEFAULT_MODEL
    suggester = getattr(request.app.state, "title_suggester", None)
    if suggester is None:
        suggester = _run_suggest_title
    suggested_title: str | None = await suggester(excerpt, model)
    if broadcaster is not None:
        tags = await _fetch_tags_out(db, session_id)
        out = _to_out(row, tags=tags)
        broadcaster.publish_upsert(out)
    return SuggestTitleOut(suggested_title=suggested_title)
