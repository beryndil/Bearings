"""Checkpoint API surface (Phase 7.2 of docs/context-menu-plan.md).

URL shape — mounted at `/api` with a per-session prefix:

  POST   /sessions/{session_id}/checkpoints              — create
  GET    /sessions/{session_id}/checkpoints              — list newest-first
  DELETE /sessions/{session_id}/checkpoints/{cid}        — remove
  POST   /sessions/{session_id}/checkpoints/{cid}/fork   — fork from anchor

The fork route reuses `store.import_session` rather than writing a new
remap path — plan §4.2 calls this out explicitly. We build the standard
`{session, messages, tool_calls}` payload, trim messages to those at or
before the anchor (`created_at` ASC cutoff), drop tool calls that belong
to trimmed messages, and hand the result to `import_session`. Fresh ids
fall out for free; the original session is never touched.

Thin handler + `store` does the work, matching `routes_checklists.py`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from bearings import metrics
from bearings.agent.sessions_broker import publish_session_upsert
from bearings.api.auth import require_auth
from bearings.api.models import (
    CheckpointCreate,
    CheckpointForkRequest,
    CheckpointOut,
    SessionOut,
)
from bearings.db import store

router = APIRouter(
    prefix="/sessions/{session_id}/checkpoints",
    tags=["checkpoints"],
    dependencies=[Depends(require_auth)],
)


async def _require_session(request: Request, session_id: str) -> dict[str, Any]:
    """Resolve the session row or raise 404. Returns the row so fork
    handlers can read title / working_dir without a second query."""
    session = await store.get_session(request.app.state.db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


async def _require_checkpoint(
    request: Request, session_id: str, checkpoint_id: str
) -> dict[str, Any]:
    """Resolve the checkpoint row, rejecting cross-session hits. The
    id is globally unique so a caller could technically fetch any
    checkpoint by id — but we scope to URL-session so a misconfigured
    frontend can't silently delete the wrong row."""
    row = await store.get_checkpoint(request.app.state.db, checkpoint_id)
    if row is None or row["session_id"] != session_id:
        raise HTTPException(status_code=404, detail="checkpoint not found")
    return row


@router.post("", response_model=CheckpointOut, status_code=201)
async def create_checkpoint(
    session_id: str, body: CheckpointCreate, request: Request
) -> CheckpointOut:
    """Anchor a new checkpoint at `body.message_id`. The message must
    belong to the same session — a cross-session anchor would be a bug
    and produces 400 here rather than waiting for a FK mismatch at
    fork time."""
    await _require_session(request, session_id)
    conn = request.app.state.db
    async with conn.execute(
        "SELECT session_id FROM messages WHERE id = ?", (body.message_id,)
    ) as cursor:
        msg_row = await cursor.fetchone()
    if msg_row is None:
        raise HTTPException(status_code=404, detail="message not found")
    if msg_row["session_id"] != session_id:
        raise HTTPException(status_code=400, detail="message does not belong to this session")
    row = await store.create_checkpoint(
        conn, session_id, message_id=body.message_id, label=body.label
    )
    metrics.checkpoints_created.inc()
    return CheckpointOut(**row)


@router.get("", response_model=list[CheckpointOut])
async def list_checkpoints(session_id: str, request: Request) -> list[CheckpointOut]:
    """Every checkpoint for a session, newest first. 404 if the session
    is unknown — an empty list means "session exists, no checkpoints"."""
    await _require_session(request, session_id)
    rows = await store.list_checkpoints(request.app.state.db, session_id)
    return [CheckpointOut(**row) for row in rows]


@router.delete("/{checkpoint_id}", status_code=204)
async def delete_checkpoint(session_id: str, checkpoint_id: str, request: Request) -> Response:
    await _require_checkpoint(request, session_id, checkpoint_id)
    ok = await store.delete_checkpoint(request.app.state.db, checkpoint_id)
    if not ok:
        # Race with a concurrent delete — surface as 404 so the client
        # reconciles rather than assuming success.
        raise HTTPException(status_code=404, detail="checkpoint not found")
    return Response(status_code=204)


def _build_fork_payload(
    session: dict[str, Any],
    anchor: dict[str, Any],
    messages: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
    *,
    title: str | None,
) -> dict[str, Any]:
    """Shape a payload for `store.import_session` out of a source
    session trimmed at the anchor message. Messages are kept if their
    `created_at` is <= the anchor's timestamp AND the id appears at-or-
    before the anchor in insertion order — the ASC list is already in
    that order, so we slice once and stop. Tool calls whose `message_id`
    falls outside the kept set get dropped so the fork doesn't carry
    orphaned tool rows."""
    cutoff = anchor["created_at"]
    kept_messages: list[dict[str, Any]] = []
    kept_ids: set[str] = set()
    for m in messages:
        if m["created_at"] > cutoff:
            break
        kept_messages.append(m)
        kept_ids.add(m["id"])
        if m["id"] == anchor["id"]:
            break
    kept_tool_calls = [tc for tc in tool_calls if tc.get("message_id") in kept_ids]
    session_payload = dict(session)
    if title is not None:
        session_payload["title"] = title
    elif session.get("title"):
        session_payload["title"] = f"{session['title']} (fork)"
    return {
        "session": session_payload,
        "messages": kept_messages,
        "tool_calls": kept_tool_calls,
    }


@router.post("/{checkpoint_id}/fork", response_model=SessionOut, status_code=201)
async def fork_checkpoint(
    session_id: str,
    checkpoint_id: str,
    body: CheckpointForkRequest,
    request: Request,
) -> SessionOut:
    """Create a new session branched from the state at this checkpoint's
    anchor message. Uses `import_session` for the message-id remap (plan
    §4.2 explicitly wants this — don't rebuild the wheel). The source
    session and its messages are never touched.

    400 when the checkpoint's anchor was orphaned (message deleted in
    a reorg audit); the UI gates the fork button on `message_id != null`
    but the server enforces it too. Inherits tags from the source so
    the fork shows up in the right sidebar bucket without a follow-up
    call."""
    conn = request.app.state.db
    source_session = await _require_session(request, session_id)
    checkpoint = await _require_checkpoint(request, session_id, checkpoint_id)
    anchor_id = checkpoint["message_id"]
    if anchor_id is None:
        raise HTTPException(
            status_code=400,
            detail="checkpoint anchor message was dropped; cannot fork",
        )
    anchor = None
    async with conn.execute(
        "SELECT id, created_at FROM messages WHERE id = ?", (anchor_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if row is not None:
            anchor = {"id": row["id"], "created_at": row["created_at"]}
    if anchor is None:
        # Race: message was deleted between SET NULL propagation and now.
        raise HTTPException(status_code=400, detail="checkpoint anchor message is gone")

    messages = await store.list_messages(conn, session_id)
    tool_calls = await store.list_tool_calls(conn, session_id)
    payload = _build_fork_payload(source_session, anchor, messages, tool_calls, title=body.title)
    new_session = await store.import_session(conn, payload)

    # Inherit source tags so the fork lands in the same sidebar bucket.
    source_tags = await store.list_session_tags(conn, session_id)
    for tag in source_tags:
        await store.attach_tag(conn, new_session["id"], tag["id"])
    # ensure_default_severity is idempotent; belt-and-braces for the case
    # where the source somehow carries no severity tag.
    await store.ensure_default_severity(conn, new_session["id"])
    metrics.sessions_created.inc()
    metrics.checkpoints_forked.inc()
    await publish_session_upsert(
        getattr(request.app.state, "sessions_broker", None), conn, new_session["id"]
    )

    refreshed = await store.get_session(conn, new_session["id"])
    assert refreshed is not None
    return SessionOut(**refreshed)
