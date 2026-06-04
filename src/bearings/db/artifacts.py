"""Artifacts table queries.

An artifact is a file path (local or remote) registered as being associated
with a session — e.g. an image produced during a run, an exported report, or
a downloaded asset.

Public surface
--------------
* :class:`ArtifactRow` — frozen dataclass row mirror.
* :func:`create` — insert a new artifact row; returns the new row.
* :func:`get` — fetch one artifact by id; ``None`` when absent.
* :func:`delete` — remove artifact row; returns ``True`` if a row was deleted.
* :func:`list_for_session` — all artifacts for a session, newest-first.
"""

from __future__ import annotations

from dataclasses import dataclass

import aiosqlite

from bearings.config.constants import ARTIFACT_ID_PREFIX
from bearings.db._id import new_id, now_iso

# ---------------------------------------------------------------------------
# Row mirror
# ---------------------------------------------------------------------------

_SELECT = "SELECT id, session_id, path, mime_type, created_at FROM artifacts"


@dataclass(frozen=True)
class ArtifactRow:
    """Immutable mirror of a single ``artifacts`` row."""

    id: str
    session_id: str
    path: str
    mime_type: str
    created_at: str


def _row_to_artifact(row: aiosqlite.Row | tuple[object, ...]) -> ArtifactRow:
    return ArtifactRow(
        id=str(row[0]),
        session_id=str(row[1]),
        path=str(row[2]),
        mime_type=str(row[3]),
        created_at=str(row[4]),
    )


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------


async def create(
    db: aiosqlite.Connection,
    *,
    session_id: str,
    path: str,
    mime_type: str,
) -> ArtifactRow:
    """Insert a new artifact row and return it.

    Raises :class:`ValueError` if ``session_id``, ``path``, or
    ``mime_type`` is empty (a content-free artifact is meaningless).
    """
    if not session_id:
        raise ValueError("session_id must be non-empty")
    if not path:
        raise ValueError("path must be non-empty")
    if not mime_type:
        raise ValueError("mime_type must be non-empty")

    artifact_id = new_id(ARTIFACT_ID_PREFIX)
    created_at = now_iso()
    await db.execute(
        "INSERT INTO artifacts (id, session_id, path, mime_type, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (artifact_id, session_id, path, mime_type, created_at),
    )
    return ArtifactRow(
        id=artifact_id,
        session_id=session_id,
        path=path,
        mime_type=mime_type,
        created_at=created_at,
    )


async def delete(db: aiosqlite.Connection, artifact_id: str) -> bool:
    """Remove the artifact row.  Returns ``True`` if a row was actually deleted."""
    cursor = await db.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


async def get(db: aiosqlite.Connection, artifact_id: str) -> ArtifactRow | None:
    """Fetch one artifact by primary key; ``None`` when absent."""
    cursor = await db.execute(_SELECT + " WHERE id = ?", (artifact_id,))
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    if row is None:
        return None
    return _row_to_artifact(row)


async def list_for_session(db: aiosqlite.Connection, session_id: str) -> list[ArtifactRow]:
    """All artifacts belonging to *session_id*, newest-first."""
    cursor = await db.execute(
        _SELECT + " WHERE session_id = ? ORDER BY created_at DESC",
        (session_id,),
    )
    try:
        rows = await cursor.fetchall()
    finally:
        await cursor.close()
    return [_row_to_artifact(r) for r in rows]


__all__ = ["ArtifactRow", "create", "delete", "get", "list_for_session"]
