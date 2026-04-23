"""Session bulk-op surface — Phase 9a of docs/context-menu-plan.md.

URL shape — mounted at `/api`:

  POST /sessions/bulk      — one endpoint, five ops

Body shape — `SessionBulkBody`:

  { "op": "tag" | "untag" | "close" | "delete" | "export",
    "ids": ["s1", "s2", ...],
    "payload": { "tag_id": 42 }        # per-op, see below }

Op contracts:

- `tag`   — `payload.tag_id` required. Attaches the tag to every id.
            Already-tagged rows are a no-op (ON CONFLICT in the store).
- `untag` — `payload.tag_id` required. Detaches the tag. Missing
            attachment is a no-op — we don't fail the whole batch.
- `close` — Stamp `closed_at = now` on every id. Already-closed rows
            refresh the timestamp; `store.close_session` is idempotent.
- `delete`— FK-cascade removal. Live runners get drained so their SDK
            subprocess doesn't outlive the row.
- `export`— Returns a bundle with one export dict per id (session +
            messages + tool_calls), same shape as the single-session
            `/sessions/{id}/export`. Unknown ids fall into `failed`
            alongside the successful bundle rows.

Every op is best-effort: per-id failures accumulate in the response's
`failed` list without aborting the rest of the batch. A client that
wants all-or-nothing semantics should one-shot the same op per id.

Thin handler — dispatches to a per-op function that calls existing
`store.*` primitives. Keeps the 400-line cap respected across both
this file and the parent `routes_sessions.py` (which was already
beyond the cap before Phase 9a started).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from bearings import metrics
from bearings.agent.sessions_broker import (
    publish_session_delete,
    publish_session_upsert,
)
from bearings.api.auth import require_auth
from bearings.api.models import (
    SessionBulkBody,
    SessionBulkResult,
    SessionExportBundle,
)
from bearings.db import store

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
    dependencies=[Depends(require_auth)],
)


async def _bulk_tag(
    request: Request, ids: list[str], tag_id: int
) -> tuple[list[str], list[dict[str, str]]]:
    conn = request.app.state.db
    if await store.get_tag(conn, tag_id) is None:
        # Bad tag blocks the whole batch — no ambiguity about what
        # succeeded since nothing did. Matches single-session behaviour.
        raise HTTPException(status_code=400, detail=f"tag_id {tag_id} does not exist")
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    for session_id in ids:
        if await store.get_session(conn, session_id) is None:
            failed.append({"id": session_id, "error": "session not found"})
            continue
        await store.attach_tag(conn, session_id, tag_id)
        succeeded.append(session_id)
        await publish_session_upsert(
            getattr(request.app.state, "sessions_broker", None), conn, session_id
        )
    return succeeded, failed


async def _bulk_untag(
    request: Request, ids: list[str], tag_id: int
) -> tuple[list[str], list[dict[str, str]]]:
    conn = request.app.state.db
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    for session_id in ids:
        if await store.get_session(conn, session_id) is None:
            failed.append({"id": session_id, "error": "session not found"})
            continue
        await store.detach_tag(conn, session_id, tag_id)
        succeeded.append(session_id)
        await publish_session_upsert(
            getattr(request.app.state, "sessions_broker", None), conn, session_id
        )
    return succeeded, failed


async def _bulk_close(request: Request, ids: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    conn = request.app.state.db
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    for session_id in ids:
        row = await store.close_session(conn, session_id)
        if row is None:
            failed.append({"id": session_id, "error": "session not found"})
            continue
        succeeded.append(session_id)
        await publish_session_upsert(
            getattr(request.app.state, "sessions_broker", None), conn, session_id
        )
    return succeeded, failed


async def _bulk_delete(request: Request, ids: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    conn = request.app.state.db
    runners = getattr(request.app.state, "runners", None)
    broker = getattr(request.app.state, "sessions_broker", None)
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    for session_id in ids:
        ok = await store.delete_session(conn, session_id)
        if not ok:
            failed.append({"id": session_id, "error": "session not found"})
            continue
        if runners is not None:
            await runners.drop(session_id)
        publish_session_delete(broker, session_id)
        succeeded.append(session_id)
    return succeeded, failed


async def _bulk_export(
    request: Request, ids: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    conn = request.app.state.db
    bundle: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for session_id in ids:
        session = await store.get_session(conn, session_id)
        if session is None:
            failed.append({"id": session_id, "error": "session not found"})
            continue
        messages = await store.list_messages(conn, session_id)
        tool_calls = await store.list_tool_calls(conn, session_id)
        bundle.append(
            {
                "session": session,
                "messages": messages,
                "tool_calls": tool_calls,
            }
        )
    return bundle, failed


def _require_tag_id(payload: dict[str, Any]) -> int:
    tag_id = payload.get("tag_id")
    if not isinstance(tag_id, int):
        raise HTTPException(
            status_code=400, detail="payload.tag_id (int) required for tag/untag ops"
        )
    return tag_id


@router.post("/bulk")
async def bulk_sessions(body: SessionBulkBody, request: Request) -> dict[str, Any]:
    """Dispatch one of five ops across a list of session ids. Returns
    `SessionBulkResult` for mutate ops and `SessionExportBundle` for
    export — both shapes carry the `op` discriminator so the frontend
    can union-type the response without a separate endpoint per op."""
    if not body.ids:
        raise HTTPException(status_code=400, detail="ids must not be empty")

    if body.op == "tag":
        tag_id = _require_tag_id(body.payload)
        succeeded, failed = await _bulk_tag(request, body.ids, tag_id)
    elif body.op == "untag":
        tag_id = _require_tag_id(body.payload)
        succeeded, failed = await _bulk_untag(request, body.ids, tag_id)
    elif body.op == "close":
        succeeded, failed = await _bulk_close(request, body.ids)
    elif body.op == "delete":
        succeeded, failed = await _bulk_delete(request, body.ids)
    elif body.op == "export":
        bundle, failed = await _bulk_export(request, body.ids)
        metrics.sessions_bulk_ops.labels(op="export").inc()
        return SessionExportBundle(sessions=bundle, failed=failed).model_dump()
    else:  # pragma: no cover — Pydantic Literal guards this
        raise HTTPException(status_code=400, detail=f"unknown op {body.op!r}")

    metrics.sessions_bulk_ops.labels(op=body.op).inc()
    return SessionBulkResult(op=body.op, succeeded=succeeded, failed=failed).model_dump()
