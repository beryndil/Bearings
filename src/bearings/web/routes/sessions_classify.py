"""Sensitive-data classification route — POST /api/sessions/{id}/spawn_classify.

T2-07: Analyzes session message history for credentials and PII, persists
the ``classified`` flag on the session row, and returns the verdict.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Request, status

from bearings.db import messages as messages_db
from bearings.db import sessions as sessions_db
from bearings.web.models.sessions import SpawnClassifyOut
from bearings.web.routes._sessions_helpers import (
    _db,
    _fetch_tags_out,
    _sessions_broadcaster,
    _to_out,
)

router = APIRouter()
_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Content-classification patterns
# ---------------------------------------------------------------------------

# Each entry is a (pattern_name, compiled_regex) pair.  A match on any
# message content sets the pattern name in the verdict.  The patterns target
# common credential and PII shapes rather than exhaustive enumeration so they
# stay readable and fast.
_CLASSIFY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # AWS access key IDs
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # Private key block headers
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    # Bearer / Authorization header values (≥20 non-space chars after the marker)
    (
        "bearer_token",
        re.compile(
            r"""(?:Authorization|Bearer)\s*[:=]?\s*["']?[A-Za-z0-9\-._~+/]{20,}""",
            re.IGNORECASE,
        ),
    ),
    # Generic api_key / secret / password / token assignment (value ≥8 chars)
    (
        "api_key",
        re.compile(
            r"""(?:api[_\-]?key|secret[_\-]?key|access[_\-]?token|password|passwd|credential)\s*[:=]\s*["']?[^\s"']{8,}""",
            re.IGNORECASE,
        ),
    ),
    # Email addresses (PII)
    ("pii_email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    # Credit card numbers (13-19 digit sequences with optional separators)
    ("pii_credit_card", re.compile(r"\b(?:\d[ \-]?){13,18}\d\b")),
]


def _classify_content(text: str) -> list[str]:
    """Return the pattern names that fire on *text*.

    Returns an empty list when no sensitive pattern matches.  The caller
    decides whether *any* match constitutes a classified verdict.
    """
    found: list[str] = []
    for name, pattern in _CLASSIFY_PATTERNS:
        if pattern.search(text):
            found.append(name)
    return found


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/api/sessions/{session_id}/spawn_classify",
    response_model=SpawnClassifyOut,
    operation_id="spawn-classify-session",
)
async def spawn_classify(session_id: str, request: Request) -> SpawnClassifyOut:
    """Analyze session messages for sensitive data and persist the classified flag (T2-07).

    Scans the full message history for credentials (API keys, bearer tokens,
    private keys, AWS keys) and PII (email addresses, credit card numbers).
    Sets ``classified = True`` on the session row when any pattern matches,
    ``False`` on a clean scan.  Returns the verdict together with the updated
    session snapshot so callers can update their local state without a second
    GET.

    The endpoint is idempotent — repeated calls re-run the scan and overwrite
    the flag with the latest result.  Returns 404 when the session does not exist.
    """
    db = _db(request)
    row = await sessions_db.get(db, session_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    # Scan all message content for sensitive patterns.
    session_messages = await messages_db.list_for_session(db, session_id)
    all_patterns: set[str] = set()
    for msg in session_messages:
        all_patterns.update(_classify_content(msg.content))

    classified_flag = bool(all_patterns)
    patterns_list = sorted(all_patterns)
    reason = (
        f"Sensitive data detected: {', '.join(patterns_list)}"
        if classified_flag
        else "No sensitive data patterns found"
    )

    updated = await sessions_db.set_classified(db, session_id, classified=classified_flag)
    if updated is None:  # pragma: no cover — row existed at top of handler
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session matches {session_id!r}",
        )
    tags = await _fetch_tags_out(db, session_id)
    out = _to_out(updated, tags=tags)
    broadcaster = _sessions_broadcaster(request)
    if broadcaster is not None:
        broadcaster.publish_upsert(out)
    return SpawnClassifyOut(
        classified=classified_flag,
        reason=reason,
        patterns_found=patterns_list,
        session=out,
    )
