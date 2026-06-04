"""Export, import, and work-evidence routes.

These endpoints deal with session data in bulk (snapshot export, restore
from export blob) or with derived evidence (git diff + tool-call summary).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter

from fastapi import APIRouter, HTTPException, Request, Response, status

from bearings.config.constants import (
    GIT_DIFF_STAT_TIMEOUT_S,
    WORK_EVIDENCE_ALL_TOOL_NAMES,
    WORK_EVIDENCE_BASH_TOOL_NAMES,
    WORK_EVIDENCE_EDIT_TOOL_NAMES,
    WORK_EVIDENCE_WRITE_TOOL_NAMES,
)
from bearings.db import checkpoints as checkpoints_db
from bearings.db import messages as messages_db
from bearings.db import sdk_entries as sdk_entries_db
from bearings.db import sessions as sessions_db
from bearings.web.models.sessions import (
    CheckpointExport,
    MessageExport,
    SessionExport,
    SessionOut,
    WorkEvidenceOut,
    WorkEvidenceToolSummary,
)
from bearings.web.routes._sessions_helpers import (
    _db,
    _fetch_tags_out,
    _sessions_broadcaster,
    _to_out,
)

router = APIRouter()
_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Export / import helpers
# ---------------------------------------------------------------------------


def _slugify(title: str) -> str:
    """Convert a session title to a safe ASCII filename stem."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "session"


async def _import_messages_and_checkpoints(
    db: object,
    body: SessionExport,
) -> None:
    """Import messages and checkpoints from an export blob; raise 422 on error."""
    import aiosqlite as _aiosqlite

    db_conn: _aiosqlite.Connection = db  # type: ignore[assignment]
    if body.messages:
        try:
            await messages_db.import_messages(
                db_conn, messages=[m.model_dump() for m in body.messages]
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
    for cp in body.checkpoints:
        try:
            await checkpoints_db.import_checkpoint(
                db_conn,
                checkpoint_id=cp.id,
                session_id=cp.session_id,
                message_id=cp.message_id,
                label=cp.label,
                created_at=cp.created_at,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc


# ---- export ----------------------------------------------------------------


@router.get("/api/sessions/{session_id}/export", operation_id="export-session")
async def export_session(session_id: str, request: Request) -> Response:
    """Snapshot-export a session to a self-contained JSON blob.

    Per ``docs/behavior/sessions.md`` §"Export contract".  Closed
    sessions are exportable.  The ``Content-Disposition`` header
    carries ``<slug>.json`` derived from the session title.
    """
    db = _db(request)
    row = await sessions_db.get(db, session_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    paired_parent_title: str | None = None
    if row.kind == "chat" and row.checklist_item_id is not None:
        info = await sessions_db.get_paired_chat_info(db, session_id)
        paired_parent_title = info[0] if info else None

    messages = await messages_db.list_for_session(db, session_id)
    tool_calls = await sdk_entries_db.load(db, session_id=session_id)
    checkpoints = await checkpoints_db.list_for_session(db, session_id)
    export_tags = await _fetch_tags_out(db, session_id)

    export = SessionExport(
        session=_to_out(row, paired_parent_title=paired_parent_title, tags=export_tags),
        messages=[
            MessageExport(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                executor_model=m.executor_model,
                advisor_model=m.advisor_model,
                effort_level=m.effort_level,
                routing_source=m.routing_source,
                routing_reason=m.routing_reason,
                matched_rule_id=m.matched_rule_id,
                executor_input_tokens=m.executor_input_tokens,
                executor_output_tokens=m.executor_output_tokens,
                advisor_input_tokens=m.advisor_input_tokens,
                advisor_output_tokens=m.advisor_output_tokens,
                advisor_calls_count=m.advisor_calls_count,
                cache_read_tokens=m.cache_read_tokens,
                cache_creation_tokens=m.cache_creation_tokens,
                input_tokens=m.input_tokens,
                output_tokens=m.output_tokens,
                seq=m.seq,
                pinned=m.pinned,
                hidden_from_context=m.hidden_from_context,
            )
            for m in messages
        ],
        tool_calls=tool_calls,
        checkpoints=[
            CheckpointExport(
                id=c.id,
                session_id=c.session_id,
                message_id=c.message_id,
                label=c.label,
                created_at=c.created_at,
            )
            for c in checkpoints
        ],
        attachments=[],
    )
    slug = _slugify(row.title)
    body = json.dumps(export.model_dump(), ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{slug}.json"'},
    )


# ---- import ----------------------------------------------------------------


@router.post(
    "/api/sessions/import",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="import-session",
)
async def import_session(
    body: SessionExport,
    request: Request,
    response: Response,
    force: bool = False,
) -> SessionOut:
    """Restore a session from an export blob.

    Per ``docs/behavior/sessions.md`` §"Import contract".
    409 when the session_id already exists and ``force=false``.
    ``checklist_item_id`` and ``template_id`` are cleared on import.
    """
    db = _db(request)
    session_id = body.session.id
    if await sessions_db.exists(db, session_id):
        if not force:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(f"session {session_id!r} already exists; pass ?force=true to overwrite"),
            )
        await sessions_db.delete(db, session_id)
        broadcaster = _sessions_broadcaster(request)
        if broadcaster is not None:
            broadcaster.publish_delete(session_id)
    s = body.session
    try:
        row = await sessions_db.import_session(
            db,
            session_id=s.id,
            kind=s.kind,
            title=s.title,
            description=s.description,
            session_instructions=s.session_instructions,
            working_dir=s.working_dir,
            model=s.model,
            permission_mode=s.permission_mode,
            max_budget_usd=s.max_budget_usd,
            total_cost_usd=s.total_cost_usd,
            message_count=len(body.messages),
            last_context_pct=s.last_context_pct,
            last_context_tokens=s.last_context_tokens,
            last_context_max=s.last_context_max,
            pinned=s.pinned,
            closed_at=s.closed_at,
            closing_summary=s.closing_summary,
            created_at=s.created_at,
            updated_at=s.updated_at,
            last_viewed_at=s.last_viewed_at,
            last_completed_at=s.last_completed_at,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    await _import_messages_and_checkpoints(db, body)
    if body.tool_calls:
        await sdk_entries_db.append(db, session_id=session_id, entries=body.tool_calls)
    imported_tags = await _fetch_tags_out(db, session_id)
    out = _to_out(row, tags=imported_tags)
    broadcaster = _sessions_broadcaster(request)
    if broadcaster is not None:
        broadcaster.publish_upsert(out)
    response.headers["Location"] = f"/api/sessions/{session_id}"
    return out


# ---- work_evidence (T2-08) -------------------------------------------------


async def _run_git_diff_stat(working_dir: str) -> str | None:
    """Run ``git diff --stat`` in ``working_dir`` with a hard timeout.

    Returns the stdout string on success; ``None`` on non-zero exit, missing
    git binary, timeout, or any OS-level error.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            working_dir,
            "diff",
            "--stat",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=GIT_DIFF_STAT_TIMEOUT_S,
        )
        if proc.returncode == 0:
            return stdout.decode(errors="replace").strip() or None
        return None
    except Exception as exc:
        _log.debug("git diff --stat error in %r: %s", working_dir, exc)
        return None


@router.get(
    "/api/sessions/{session_id}/work_evidence",
    response_model=WorkEvidenceOut,
    operation_id="get-session-work-evidence",
)
async def get_work_evidence(session_id: str, request: Request) -> WorkEvidenceOut:
    """Return a structured summary of work performed by the session (T2-08).

    Queries ``tool_calls`` for bash, write, and edit invocations, then
    optionally runs ``git diff --stat``.  ``app.state.git_diff_runner``
    overrides the subprocess in tests.  Always returns 200.
    """
    db = _db(request)
    row = await sessions_db.get(db, session_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    placeholders = ",".join("?" * len(WORK_EVIDENCE_ALL_TOOL_NAMES))
    cursor = await db.execute(
        f"SELECT tool_name FROM tool_calls "
        f"WHERE session_id = ? AND tool_name IN ({placeholders}) "
        f"ORDER BY rowid ASC",
        (session_id, *sorted(WORK_EVIDENCE_ALL_TOOL_NAMES)),
    )
    try:
        rows = await cursor.fetchall()
    finally:
        await cursor.close()
    name_counts: Counter[str] = Counter(str(r[0]) for r in rows)
    bash_calls = sum(name_counts[n] for n in WORK_EVIDENCE_BASH_TOOL_NAMES)
    write_calls = sum(name_counts[n] for n in WORK_EVIDENCE_WRITE_TOOL_NAMES)
    edit_calls = sum(name_counts[n] for n in WORK_EVIDENCE_EDIT_TOOL_NAMES)
    tool_calls_summary = [
        WorkEvidenceToolSummary(tool_name=name, call_count=count)
        for name, count in sorted(name_counts.items())
        if count > 0
    ]
    git_runner = getattr(request.app.state, "git_diff_runner", None)
    if git_runner is None:
        git_runner = _run_git_diff_stat
    git_diff_stat: str | None = await git_runner(row.working_dir)
    return WorkEvidenceOut(
        tool_calls_summary=tool_calls_summary,
        bash_calls=bash_calls,
        write_calls=write_calls,
        edit_calls=edit_calls,
        total_work_tool_calls=bash_calls + write_calls + edit_calls,
        git_diff_stat=git_diff_stat,
        git_diff_available=bool(git_diff_stat),
    )
