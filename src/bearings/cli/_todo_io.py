"""TODO.md walker + parser — internal helper module.

Per ``docs/behavior/bearings-cli.md`` §"bearings todo" the four
subcommands "walk the project tree starting from the CWD" looking for
``TODO.md`` files. This module owns the walking + per-file parsing
so the user-facing subcommands stay thin.

The leading underscore in the filename signals module-private status
per arch §1.1.3's import-rule convention: cross-package imports are a
violation; the consumer is :mod:`bearings.cli.todo` only.

TODO.md grammar (per ``CLAUDE.md`` §"TODO.md Discipline" + the
beryndil-charter convention used across projects):

* H1 ``# Title`` — file title (one per file, optional, ignored at
  parse time).
* H2 ``## Heading`` — entry boundary. Each H2 starts a new entry; the
  body extends to the next H2 (or EOF).
* Body markup is free-form Markdown. The parser extracts:
  * ``status: <Open|In Progress|Blocked>`` line — the entry's status
    label (default ``Open`` if absent);
  * ``area: <foo>`` line — the entry's classification (default
    ``""`` if absent);
  * The first non-status / non-area line of the body — surfaced as
    a one-line summary in ``--format text`` output.

The grammar is intentionally lenient: a malformed entry surfaces as
``status="Open"`` with whatever text the parser found. Stricter
validation lives in ``bearings todo check`` (which lints rather than
parses).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from bearings.config.constants import (
    BEARINGS_TODO_ENTRY_HEADING_PREFIX,
    BEARINGS_TODO_FILENAME,
    BEARINGS_TODO_WALK_MAX_DEPTH,
)

# Default status the parser assigns when an entry has no ``status:``
# line. Per ``CLAUDE.md`` §"TODO.md Discipline" — "Open" is the
# starting state for a fresh deferral; the convention surfaces in
# every project's TODO.md.
DEFAULT_TODO_STATUS: str = "Open"

# Status alphabet the linter recognises. A malformed status (e.g.
# ``status: Maybe``) is reported as a check finding but parses
# through with the literal value.
KNOWN_TODO_STATUSES: frozenset[str] = frozenset({"Open", "In Progress", "Blocked", "Done"})


@dataclass(frozen=True)
class TodoEntry:
    """One ``## Heading`` entry parsed from a TODO.md file.

    Frozen so a downstream sort by ``mtime`` / ``status`` runs without
    aliasing surprises.

    Field semantics:

    * ``file`` — the absolute path to the source TODO.md.
    * ``title`` — text after the H2 ``##`` prefix, trimmed.
    * ``status`` — the status label (``"Open"`` / ``"In Progress"`` /
      ``"Blocked"`` / ``"Done"`` typical; raw value preserved).
    * ``area`` — the area classification, or ``""`` if absent.
    * ``summary`` — first non-meta body line, or ``""`` for
      header-only entries.
    * ``body`` — every body line joined with ``\\n``; preserves the
      original whitespace-trimmed body so the JSON output can
      reproduce the original.
    * ``line_number`` — 1-indexed line of the H2 heading; used in
      check findings to point at offending entries.
    * ``mtime`` — file's mtime in unix seconds, propagated from the
      walker; used by ``bearings todo recent`` for the N-day filter.
    """

    file: Path
    title: str
    status: str
    area: str
    summary: str
    body: str
    line_number: int
    mtime: float


def walk_todo_files(
    root: Path,
    *,
    max_depth: int = BEARINGS_TODO_WALK_MAX_DEPTH,
) -> list[Path]:
    """Walk ``root`` for ``TODO.md`` files (depth-bounded).

    Per behavior doc §"bearings todo" — the walker starts from the
    user's CWD; the depth bound is the
    :data:`bearings.config.constants.BEARINGS_TODO_WALK_MAX_DEPTH`
    decided-and-documented limit. Hidden directories (``.git``,
    ``.venv``, etc.) are skipped so the walker never descends into
    package-manager caches.

    Returns: absolute paths sorted alphabetically (deterministic for
    the test suite + downstream pipelines).
    """
    if not root.exists():
        return []
    found: list[Path] = []
    root_resolved = root.resolve()
    root_depth = len(root_resolved.parts)
    for current_dir, subdirs, filenames in os.walk(root_resolved):
        # Prune hidden subdirs in place so os.walk does not descend.
        subdirs[:] = [d for d in subdirs if not d.startswith(".")]
        # Depth-cap: stop walking below BEARINGS_TODO_WALK_MAX_DEPTH
        # levels under root.
        depth = len(Path(current_dir).parts) - root_depth
        if depth >= max_depth:
            subdirs.clear()
        if BEARINGS_TODO_FILENAME in filenames:
            found.append(Path(current_dir) / BEARINGS_TODO_FILENAME)
    found.sort()
    return found


def parse_todo_file(path: Path) -> list[TodoEntry]:
    """Parse one ``TODO.md`` into its H2 entries.

    Lenient grammar (see module docstring): malformed entries surface
    with ``status="Open"`` and whatever text the parser found. Empty
    files (or files with no H2 headings) produce an empty list.

    Raises:
        FileNotFoundError: ``path`` does not exist (the walker
            shouldn't surface paths that vanished, but the parser is
            defensive against a race between walk + parse).
        OSError: the file is unreadable for reasons other than
            missing — surfaced for the operation-level failure path.
    """
    text = path.read_text(encoding="utf-8")
    mtime = path.stat().st_mtime
    entries: list[TodoEntry] = []
    lines = text.splitlines()
    current_title: str | None = None
    current_line_number: int = 0
    current_body: list[str] = []
    for line_index, line in enumerate(lines, start=1):
        if line.startswith(BEARINGS_TODO_ENTRY_HEADING_PREFIX):
            # Flush the previous entry.
            if current_title is not None:
                entries.append(
                    _build_entry(
                        path=path,
                        mtime=mtime,
                        title=current_title,
                        line_number=current_line_number,
                        body_lines=current_body,
                    )
                )
            current_title = line[len(BEARINGS_TODO_ENTRY_HEADING_PREFIX) :].strip()
            current_line_number = line_index
            current_body = []
        elif current_title is not None:
            # H1 above the first H2 is ignored; body lines accumulate
            # on the current entry.
            current_body.append(line)
    if current_title is not None:
        entries.append(
            _build_entry(
                path=path,
                mtime=mtime,
                title=current_title,
                line_number=current_line_number,
                body_lines=current_body,
            )
        )
    return entries


def parse_all(paths: list[Path]) -> list[TodoEntry]:
    """Parse every file in ``paths`` and concatenate the results.

    Files that fail to parse (missing / unreadable) are skipped with
    an :class:`OSError` re-raised to the caller — the CLI top-level
    wraps the call with a one-shot error path so the user sees a
    stderr message + exit 1.
    """
    all_entries: list[TodoEntry] = []
    for path in paths:
        all_entries.extend(parse_todo_file(path))
    return all_entries


def _build_entry(
    *,
    path: Path,
    mtime: float,
    title: str,
    line_number: int,
    body_lines: list[str],
) -> TodoEntry:
    """Assemble a :class:`TodoEntry` from its raw parts."""
    status = DEFAULT_TODO_STATUS
    area = ""
    summary = ""
    seen_summary = False
    body_kept: list[str] = []
    for raw in body_lines:
        stripped = raw.strip()
        if not stripped:
            body_kept.append(raw)
            continue
        # ``status:`` / ``area:`` meta lines (case-insensitive on the
        # key, value passed through verbatim trimmed).
        lower = stripped.lower()
        if lower.startswith("status:"):
            status = stripped.split(":", 1)[1].strip() or DEFAULT_TODO_STATUS
            body_kept.append(raw)
            continue
        if lower.startswith("area:"):
            area = stripped.split(":", 1)[1].strip()
            body_kept.append(raw)
            continue
        if not seen_summary:
            summary = stripped
            seen_summary = True
        body_kept.append(raw)
    return TodoEntry(
        file=path,
        title=title,
        status=status,
        area=area,
        summary=summary,
        body="\n".join(body_kept).strip("\n"),
        line_number=line_number,
        mtime=mtime,
    )


def filter_by_status(entries: list[TodoEntry], statuses: frozenset[str]) -> list[TodoEntry]:
    """Return only entries whose ``status`` is in ``statuses``."""
    return [entry for entry in entries if entry.status in statuses]


def filter_by_area(entries: list[TodoEntry], area: str) -> list[TodoEntry]:
    """Return only entries whose ``area`` equals ``area`` (exact match)."""
    return [entry for entry in entries if entry.area == area]


__all__ = [
    "DEFAULT_TODO_STATUS",
    "KNOWN_TODO_STATUSES",
    "TodoEntry",
    "filter_by_area",
    "filter_by_status",
    "parse_all",
    "parse_todo_file",
    "walk_todo_files",
]
