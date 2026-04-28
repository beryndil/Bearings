"""Module-private id and timestamp helpers for the ``bearings.db`` package.

Per ``docs/architecture-v1.md`` §1.1.3 the leading underscore is the
import-rule signal: cross-package imports of ``_id`` are a lint
violation. Concern-module authors inside :mod:`bearings.db` import these
helpers; downstream layers (``bearings.agent`` / ``bearings.web``)
construct ids/timestamps via the wire shape callers expect rather than
reaching into this private surface.

Two helpers:

* :func:`new_id` — random TEXT primary-key generator with a per-table
  prefix so a stray id leaking into a log line is self-describing
  (``cpt_…`` for checkpoints, ``msg_…`` for messages, etc.).
* :func:`now_iso` — ISO-8601 UTC timestamp string with offset, matching
  the ``schema.sql`` convention for the user-facing tables (``sessions``,
  ``messages``, ``checklist_items``, ``checkpoints``, ``templates``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from secrets import token_hex
from typing import Final

# Random ID width in bytes (32 hex chars at ``hex()``); chosen wide
# enough that the birthday-collision floor for any single session's
# checkpoints is astronomically remote without producing unwieldy IDs in
# logs and gutter-chip "Copy checkpoint ID" output.
_ID_RANDOM_BYTES: Final[int] = 16


def new_id(prefix: str) -> str:
    """Return ``<prefix>_<32-hex>`` for a fresh row primary key.

    Raises :class:`ValueError` on an empty prefix so that a renamed
    table cannot silently drop the prefix. The prefix is the only part
    a future grep or log inspection sees, so it is load-bearing.
    """
    if not prefix:
        raise ValueError("new_id prefix must be non-empty")
    return f"{prefix}_{token_hex(_ID_RANDOM_BYTES)}"


def now_iso() -> str:
    """Return the current UTC instant as ``YYYY-MM-DDTHH:MM:SS.ffffff+00:00``.

    Matches the ISO-8601-with-offset shape ``schema.sql`` declares for
    every TEXT timestamp column on the user-facing tables. ``timespec=
    'microseconds'`` is required (not ``'seconds'``) so that two rows
    written within the same second still sort deterministically by
    ``created_at`` — the ``checkpoints`` and ``templates`` query
    modules sort by ``created_at DESC`` to surface newest-first, and
    second-resolution timestamps would tie repeatedly under a fast
    test loop or a burst of user actions. Lexicographic ordering of
    the resulting strings matches chronological order because
    ``microseconds`` widens the seconds field uniformly.
    """
    return datetime.now(tz=UTC).isoformat(timespec="microseconds")


__all__ = ["new_id", "now_iso"]
