"""Phase 15 — `POST /sessions/{id}/regenerate_from/{message_id}`.

Decision §8.4: fork-only for v1; rewrite-in-place stays disabled. This
route walks the source session's messages back to the user-turn
boundary at-or-before `message_id`, copies messages [1..boundary-1]
into a brand-new session via `store.import_session`, inherits parent
tags + permission_mode, prefixes the new session's title with
`↳ regen: `, and returns BOTH the new session row AND the boundary
user-message text so the frontend can seed its composer for re-send.

The boundary user message itself is NOT copied into the new session.
The frontend re-issues it as the first prompt of the fork against a
fresh `sdk_session_id` minted by the SDK on first turn — that's how
we avoid the rewound-history SDK problem entirely (we never rewind a
live session, we always start fresh in a new one).

Mirrors `routes_checkpoints.fork_checkpoint` heavily: same
`store.import_session` reuse, same tag/severity inheritance, same
upsert publish so the sidebar receives the new row immediately. The
permission_mode inheritance is the one extra step the checkpoint fork
doesn't do; without it a `safe`-profile session would lose its
permission_mode on regenerate, which would surprise the user.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from bearings import metrics
from bearings.agent.sessions_broker import publish_session_upsert
from bearings.api.auth import require_auth
from bearings.api.models import RegenerateFromMessageOut, SessionOut
from bearings.db import store

router = APIRouter(
    prefix="/sessions",
    tags=["regenerate"],
    dependencies=[Depends(require_auth)],
)


_REGEN_TITLE_PREFIX = "↳ regen: "


def _find_boundary(messages: list[dict[str, Any]], target_id: str) -> dict[str, Any] | None:
    """Walk `messages` (chronological ASC) and return the user-role row
    at-or-before the target message. None when no user row exists in
    that range. Caller treats None as 400 — there's nothing to
    regenerate from on an assistant-only prefix."""
    target_idx: int | None = None
    for i, m in enumerate(messages):
        if m["id"] == target_id:
            target_idx = i
            break
    if target_idx is None:
        return None
    for i in range(target_idx, -1, -1):
        if messages[i]["role"] == "user":
            return messages[i]
    return None


def _build_payload(
    source_session: dict[str, Any],
    boundary: dict[str, Any],
    messages: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """Trim messages to those strictly BEFORE the boundary user-turn,
    drop tool_calls whose `message_id` belongs to a dropped row, and
    wrap into the `store.import_session` shape. The boundary message
    itself is excluded — the frontend re-sends it as the first prompt
    of the fork against a fresh sdk_session_id."""
    cutoff = boundary["created_at"]
    boundary_id = boundary["id"]
    kept_messages: list[dict[str, Any]] = []
    kept_ids: set[str] = set()
    for m in messages:
        if m["id"] == boundary_id:
            break
        if m["created_at"] >= cutoff:
            # Tie-breaker: a row with the same timestamp as boundary but
            # a different id was inserted later in the same millisecond.
            # We've already passed the boundary in id-order (ASC list),
            # so anything here belongs to a later turn — skip.
            continue
        kept_messages.append(m)
        kept_ids.add(m["id"])
    kept_tool_calls = [tc for tc in tool_calls if tc.get("message_id") in kept_ids]
    src_title = source_session.get("title") or ""
    new_title = f"{_REGEN_TITLE_PREFIX}{src_title}" if src_title else _REGEN_TITLE_PREFIX.strip()
    session_payload = dict(source_session)
    session_payload["title"] = new_title
    # Don't carry closed_at forward — a regenerate should land in the
    # open sessions group regardless of whether the parent was closed.
    session_payload["closed_at"] = None
    return {
        "session": session_payload,
        "messages": kept_messages,
        "tool_calls": kept_tool_calls,
    }


@router.post(
    "/{session_id}/regenerate_from/{message_id}",
    response_model=RegenerateFromMessageOut,
    status_code=201,
)
async def regenerate_from_message(
    session_id: str,
    message_id: str,
    request: Request,
) -> RegenerateFromMessageOut:
    """Fork at the user-turn boundary at-or-before `message_id` and
    return the new session plus the boundary user-prompt text.

    400 when the target message is not in this session, or when no
    user-role boundary exists at-or-before the target. 404 when either
    id is unknown.
    """
    conn = request.app.state.db
    source_session = await store.get_session(conn, session_id)
    if source_session is None:
        raise HTTPException(status_code=404, detail="session not found")

    async with conn.execute(
        "SELECT id, session_id FROM messages WHERE id = ?", (message_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="message not found")
    if row["session_id"] != session_id:
        raise HTTPException(status_code=400, detail="message does not belong to this session")

    messages = await store.list_messages(conn, session_id)
    boundary = _find_boundary(messages, message_id)
    if boundary is None:
        raise HTTPException(
            status_code=400,
            detail="no user-turn at or before this message; nothing to regenerate",
        )

    tool_calls = await store.list_tool_calls(conn, session_id)
    payload = _build_payload(source_session, boundary, messages, tool_calls)
    new_session = await store.import_session(conn, payload)

    # Inherit tags + permission_mode from the source. Tag attach mirrors
    # the checkpoint-fork path; permission_mode is the extra step we do
    # because import_session doesn't carry it forward (it lives in a
    # separate column writer).
    source_tags = await store.list_session_tags(conn, session_id)
    for tag in source_tags:
        await store.attach_tag(conn, new_session["id"], tag["id"])
    await store.ensure_default_severity(conn, new_session["id"])
    src_pm = source_session.get("permission_mode")
    if src_pm:
        await store.set_session_permission_mode(conn, new_session["id"], src_pm)

    metrics.sessions_created.inc()
    await publish_session_upsert(
        getattr(request.app.state, "sessions_broker", None), conn, new_session["id"]
    )

    refreshed = await store.get_session(conn, new_session["id"])
    assert refreshed is not None
    return RegenerateFromMessageOut(
        session=SessionOut(**refreshed),
        prompt=str(boundary.get("content") or ""),
    )
