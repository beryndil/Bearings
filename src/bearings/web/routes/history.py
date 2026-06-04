# mypy: disable-error-code=explicit-any
"""Directory-context history.jsonl reader (arch §1.1.5) + full DB export.

Two endpoint groups:

* ``GET /api/history/jsonl?directory=<path>`` — reads the ``history.jsonl``
  file from the ``.bearings/`` sub-directory of *directory* and returns
  its entries as a JSON array (see :class:`DirectoryHistoryEntry`).

* ``GET /api/history/export`` — dumps **all** sessions, their messages, and
  their associated tags as a single JSON payload.  Intended for backup and
  portability tooling.  Returns 503 when no DB connection is configured.

Result shape (jsonl endpoint)
------------------------------
Each entry is a :class:`~bearings.web.models.history.DirectoryHistoryEntry`:

* ``event`` — event kind string (e.g. ``"context_start"``).
* ``session_id`` — the session that triggered the event, or ``None``.
* ``timestamp`` — ISO-8601 timestamp.

Unknown fields from future event types are silently dropped so older
clients remain forward-compatible.

Graceful degradation (jsonl endpoint)
--------------------------------------
Returns an empty list when the file does not exist (directory not yet
onboarded) rather than raising 404, so callers can treat the response
uniformly without special-casing the first-time case.

The optional ``limit`` parameter (default:
:data:`~bearings.config.constants.BEARINGS_DIR_HISTORY_CAP`) controls
how many of the most-recent entries are returned.  Entries are ordered
oldest-first in the file; the *limit* newest are selected before
returning.

Export endpoint shape
---------------------
::

    {
        "sessions": [ { ...session fields... }, ... ],
        "messages": { "<session_id>": [ { ...message fields... }, ... ] },
        "tags":     { "<session_id>": [ { ...tag fields... }, ... ] }
    }
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from bearings.bearings_dir import io as bdir_io
from bearings.config.constants import (
    BEARINGS_DIR_HISTORY_CAP,
    BEARINGS_DIR_HISTORY_FILENAME,
    BEARINGS_DIR_SUBDIR,
)
from bearings.db import messages as messages_db
from bearings.db import sessions as sessions_db
from bearings.db import tags as tags_db
from bearings.web.models.history import DirectoryHistoryEntry
from bearings.web.routes._deps import _db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/api/history/jsonl",
    response_model=list[DirectoryHistoryEntry],
    operation_id="get-directory-history",
    summary="Get .bearings/history.jsonl entries for a directory",
)
async def get_directory_history(
    directory: Annotated[
        str,
        Query(description="Absolute path to the project directory whose history to read."),
    ],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=BEARINGS_DIR_HISTORY_CAP,
            description=(
                "Maximum number of entries to return (most-recent first within the cap). "
                f"Defaults to {BEARINGS_DIR_HISTORY_CAP}."
            ),
        ),
    ] = BEARINGS_DIR_HISTORY_CAP,
) -> list[DirectoryHistoryEntry]:
    """Return ``history.jsonl`` entries for *directory*.

    Delegates to :func:`bearings.bearings_dir.io.read_jsonl`.  Returns an
    empty list when the file does not exist — directory not yet onboarded.
    Malformed individual entries are skipped rather than raising so a single
    corrupted line never breaks the whole read.
    """
    history_path = Path(directory) / BEARINGS_DIR_SUBDIR / BEARINGS_DIR_HISTORY_FILENAME
    raw_entries = bdir_io.read_jsonl(history_path)
    # Apply limit against the tail (most-recent entries).
    sliced = raw_entries[-limit:]
    results: list[DirectoryHistoryEntry] = []
    for entry in sliced:
        try:
            results.append(DirectoryHistoryEntry.model_validate(entry))
        except Exception:
            logger.debug("read_directory_history: skipping malformed entry %r", entry)
    return results


# ---------------------------------------------------------------------------
# Export — full DB dump (sessions + messages + tags)
# ---------------------------------------------------------------------------


class _TagItem(BaseModel):
    id: int
    name: str
    color: str | None


class _MessageItem(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class _SessionItem(BaseModel):
    id: str
    kind: str
    title: str
    working_dir: str
    model: str
    created_at: str
    updated_at: str
    closed_at: str | None


class HistoryExportOut(BaseModel):
    """Full history export payload."""

    sessions: list[_SessionItem]
    messages: dict[str, list[_MessageItem]]
    tags: dict[str, list[_TagItem]]


@router.get(
    "/api/history/export",
    response_model=HistoryExportOut,
    operation_id="export-history",
    summary="Export all sessions, messages, and tags as JSON",
)
async def export_history(request: Request) -> HistoryExportOut:
    """Return every session, its messages, and its tags in a single payload.

    Returns 503 when no DB connection is configured.  For large instances
    this may be slow (O(sessions) DB round-trips); intended for backup /
    portability use rather than real-time queries.
    """
    db = _db(request)
    all_sessions = await sessions_db.list_all(db)
    session_items: list[_SessionItem] = [
        _SessionItem(
            id=s.id,
            kind=s.kind,
            title=s.title,
            working_dir=s.working_dir,
            model=s.model,
            created_at=s.created_at,
            updated_at=s.updated_at,
            closed_at=s.closed_at,
        )
        for s in all_sessions
    ]

    messages_map: dict[str, list[_MessageItem]] = {}
    tags_map: dict[str, list[_TagItem]] = {}

    for session in all_sessions:
        msgs = await messages_db.list_for_session(db, session.id)
        messages_map[session.id] = [
            _MessageItem(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in msgs
        ]
        session_tags = await tags_db.list_for_session(db, session.id)
        tags_map[session.id] = [_TagItem(id=t.id, name=t.name, color=t.color) for t in session_tags]

    return HistoryExportOut(
        sessions=session_items,
        messages=messages_map,
        tags=tags_map,
    )


__all__ = ["router"]
