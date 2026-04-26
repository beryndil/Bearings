"""L4.3.2 — `POST /sessions/{id}/invoke_reply_action/{message_id}`.

Wave 2 lane 2 of the assistant-reply action row (TODO.md). The route
backs the `✂ TLDR` button (and L4.3.3's `⚔ CRIT`): the frontend POSTs
an action name + the target message id, the server validates the
message, spawns a fresh tool-less sub-agent via
`bearings.agent.sub_invoke.run_reply_action`, and streams the model's
text deltas straight back over Server-Sent Events.

Why SSE and not the existing WS event path:

1.  The sub-agent run is ephemeral, scoped to one HTTP request — the
    modal opens, streams, closes. Routing tokens through the runner's
    `/ws/{session_id}` channel would force every wire event to grow a
    `sub_invocation_id` (so subscribers can demux preview tokens from
    real-turn tokens), or we'd attribute sub-agent tokens to a fake
    session id. Both are worse than a per-request stream.
2.  No persistence layer means no need for the runner's ring buffer.
    Reconnect-resume is irrelevant; if the modal closes, the call
    cancels.
3.  `text/event-stream` is trivial to consume — the frontend uses
    `fetch` + a streaming reader (rather than the spec's `EventSource`,
    which can't carry an Authorization header for our bearer auth).

Cost attribution rolls into the parent session's `total_cost_usd` via
`add_session_cost` inside `run_reply_action`. L2.1's `max_budget_usd`
gate is *not* re-checked here — it applies to the parent runner's
pre-turn submit, and a sub-invocation costs cents at most. Future
"tools budget" (deferred from L2.1 plan) is the right place to add a
separate cap.

Result is *ephemeral*: nothing persists in `messages` or any new
table. The modal owns the lifecycle. "Send to composer" lets the
user promote the result if they want it kept; otherwise it's gone on
modal close. Future deferred follow-up: a `reply_actions` table with
a FK into `messages`, indexed by `(session_id, message_id, action,
created_at)`, if usage shows we want history.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from bearings.agent.sub_invoke import (
    ACTION_LABELS,
    Complete,
    Failure,
    SubInvokeEvent,
    TextChunk,
    is_known_action,
    run_reply_action,
)
from bearings.api.auth import require_auth
from bearings.db import store

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sessions",
    tags=["reply-actions"],
    dependencies=[Depends(require_auth)],
)


class InvokeReplyActionBody(BaseModel):
    """POST body for the invoke endpoint. `action` is the enum entry
    from `sub_invoke.PROMPT_TEMPLATES`; `model` lets the caller
    override the default (= parent session's model). Keeping `model`
    optional means the v0 frontend doesn't have to think about it.
    """

    action: str = Field(..., description="Reply-action name; must match a known prompt template.")
    model: str | None = Field(
        default=None,
        description="Override the parent session's model. Defaults to inheriting it.",
    )


def _sse_frame(event: str, data: dict[str, object]) -> bytes:
    """Encode one SSE frame. The `\\n\\n` terminator is what tells the
    EventSource parser the frame is complete. JSON-encoded payload
    keeps the consumer's parsing path uniform across event types — no
    per-event ad-hoc decoding."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode()


def _serialize(event: SubInvokeEvent) -> bytes:
    """Map a sub-invoke event to its SSE wire frame. Matches the
    discriminator the frontend expects — `token` carries `{text}`,
    `complete` carries `{cost_usd, full_text}`, `error` carries
    `{message}`."""
    if isinstance(event, TextChunk):
        return _sse_frame("token", {"text": event.text})
    if isinstance(event, Complete):
        return _sse_frame("complete", asdict(event))
    if isinstance(event, Failure):
        return _sse_frame("error", {"message": event.message})
    raise TypeError(f"unhandled sub-invoke event type: {type(event).__name__}")


@router.get("/reply_actions/catalog")
async def list_reply_actions() -> dict[str, dict[str, str]]:
    """Expose the action catalog so the frontend can render labels
    without hardcoding the enum. Returns `{action: {label}}`. Adding
    a new action (e.g. L4.3.3's `critique`) updates the catalog
    automatically as long as `ACTION_LABELS` gets the new entry."""
    return {action: {"label": label} for action, label in ACTION_LABELS.items()}


@router.post(
    "/{session_id}/invoke_reply_action/{message_id}",
    responses={
        200: {"description": "SSE stream of token / complete / error events."},
        400: {"description": "Unknown action, or message is not an assistant turn."},
        404: {"description": "Session or message not found."},
    },
)
async def invoke_reply_action(
    session_id: str,
    message_id: str,
    body: InvokeReplyActionBody,
    request: Request,
) -> StreamingResponse:
    """Stream a sub-agent invocation against `message_id`'s reply.

    400 when:
      - the action name isn't in the registered catalog
      - the message doesn't belong to this session
      - the message isn't an assistant turn (we only summarize/critique
        replies, never user prompts — there's no useful semantics there)
    404 when either id is unknown.
    """
    if not is_known_action(body.action):
        raise HTTPException(
            status_code=400,
            detail=f"unknown action: {body.action!r}",
        )
    conn = request.app.state.db
    parent = await store.get_session(conn, session_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="session not found")

    async with conn.execute(
        "SELECT id, session_id, role, content FROM messages WHERE id = ?",
        (message_id,),
    ) as cursor:
        msg_row = await cursor.fetchone()
    if msg_row is None:
        raise HTTPException(status_code=404, detail="message not found")
    if msg_row["session_id"] != session_id:
        raise HTTPException(
            status_code=400,
            detail="message does not belong to this session",
        )
    if msg_row["role"] != "assistant":
        raise HTTPException(
            status_code=400,
            detail="invoke_reply_action requires an assistant message",
        )

    source_text = str(msg_row["content"] or "")
    model = body.model or str(parent["model"])
    working_dir = str(parent["working_dir"])

    async def event_iter() -> AsyncIterator[bytes]:
        """Bridge the sub-invoke generator to the SSE wire. A ping
        comment frame opens the stream so proxies that buffer until
        first byte (rare on localhost, but cheap insurance) flush
        promptly. We swallow the per-frame encode errors at the
        highest layer — a malformed event would mean a bug in
        `_serialize` and is best surfaced as a server-side log entry,
        not a partial stream."""
        # SSE comment line — clients ignore lines starting with `:`,
        # but it forces the response headers to flush so the modal
        # can switch from "spinning" to "streaming" before the model
        # produces its first token.
        yield b": stream-open\n\n"
        try:
            async for event in run_reply_action(
                action=body.action,
                source_text=source_text,
                working_dir=working_dir,
                model=model,
                db=conn,
                parent_session_id=session_id,
            ):
                yield _serialize(event)
        except Exception as exc:  # noqa: BLE001 — convert to wire-level error
            log.exception("reply-action %s crashed mid-stream", body.action)
            yield _sse_frame("error", {"message": str(exc) or "stream crashed"})

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            # Disable proxy / browser caching of the stream itself —
            # SSE responses are by definition not cacheable.
            "Cache-Control": "no-cache",
            # Hint to nginx-style reverse proxies (and our localhost
            # static handler) to skip output buffering. Belt-and-
            # suspenders for the SSE comment ping above.
            "X-Accel-Buffering": "no",
        },
    )
