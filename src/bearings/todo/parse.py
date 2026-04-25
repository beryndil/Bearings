"""TodoEntry parsing per spec §1 + discovery walker per §2.2.

The authoritative regexes (§1.3) live here as the single source of truth
shared by all subcommands. ``TodoEntry`` carries enough diagnostic state
(per-field line numbers, duplicate flags, ordering) for ``lint.py`` to
emit each E00N / W10N rule from §2.5 without re-parsing the file.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# --- §1.3 authoritative regexes (spec-locked, do not loosen) ------------

ENTRY_SPLIT = re.compile(r"^---\s*$", re.MULTILINE)
H2_TITLE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
STATUS_LINE = re.compile(
    r"^\*\*Status:\*\*\s+(?P<status>Open|Blocked|In Progress)\s*$",
    re.MULTILINE,
)
LOGGED_LINE = re.compile(
    r"^\*\*Logged:\*\*\s+(?P<logged>\d{4}-\d{2}-\d{2}|unknown)\s*$",
    re.MULTILINE,
)
AREA_LINE = re.compile(r"^\*\*Area:\*\*\s*(?P<area>.*?)\s*$", re.MULTILINE)

# --- Diagnostic labels (looser — used to detect malformed values) -------
# A line that *claims* to be a Status/Logged/Area field but whose value
# fails the strict regex still needs a stable line number for an E004 /
# E005 finding.
LABEL_STATUS = re.compile(r"^\*\*Status:\*\*\s*(?P<value>.*?)\s*$")
LABEL_LOGGED = re.compile(r"^\*\*Logged:\*\*\s*(?P<value>.*?)\s*$")
LABEL_AREA = re.compile(r"^\*\*Area:\*\*\s*(?P<value>.*?)\s*$")

STATUS_VALUES: tuple[str, ...] = ("Open", "Blocked", "In Progress")

# --- §2.2 discovery skip-list (spec-locked) ------------------------------

SKIP_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "dist",
        "build",
        ".next",
        "__pycache__",
        ".venv",
        "venv",
        ".cache",
        ".turbo",
        "coverage",
        "_archive",
    }
)


@dataclass(frozen=True)
class FieldRecord:
    """One Status/Logged/Area line as it appeared in the source."""

    line_number: int
    raw_value: str
    value_valid: bool


@dataclass(frozen=True)
class TodoEntry:
    """One H2 entry in a TODO.md file."""

    file_path: Path
    title: str
    title_line: int
    status_field: FieldRecord | None
    logged_field: FieldRecord | None
    area_field: FieldRecord | None
    duplicate_status: bool
    duplicate_logged: bool
    duplicate_area: bool
    header_in_order: bool
    body: str

    @property
    def status(self) -> str | None:
        f = self.status_field
        return f.raw_value if f and f.value_valid else None

    @property
    def logged_raw(self) -> str | None:
        f = self.logged_field
        return f.raw_value if f and f.value_valid else None

    @property
    def logged_date(self) -> date | None:
        raw = self.logged_raw
        if raw is None or raw == "unknown":
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None

    @property
    def area(self) -> str | None:
        f = self.area_field
        return f.raw_value if f else None


def discover_todo_files(root: Path) -> list[Path]:
    """Walk root downward and return every live ``TODO.md`` path.

    Skips directories named in ``SKIP_DIR_NAMES`` at any depth. Does not
    follow symlinks. Files like ``TODO-archive-*.md`` and ``TODO.md.bak``
    are skipped automatically because the filename match is exact.
    """
    out: list[Path] = []
    for current_dir, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        if "TODO.md" in filenames:
            out.append(Path(current_dir) / "TODO.md")
    out.sort()
    return out


def parse_file(path: Path) -> list[TodoEntry]:
    """Parse one TODO.md file. Returns an empty list when the file is
    unreadable as UTF-8 (callers treat unreadable files as exit-2 usage
    errors at the CLI boundary)."""
    text = path.read_text(encoding="utf-8")
    return parse_text(path, text)


def parse_text(path: Path, text: str) -> list[TodoEntry]:
    """Parse all H2 entries in ``text``.

    An entry runs from its ``## title`` line to (exclusive of) the next
    ``## title`` line, ``---``-only line, or EOF. Header fields are
    detected only in the entry's body prefix that precedes any non-blank,
    non-field line — this is what §1.3's "consecutive non-blank lines"
    rule means in operational terms.
    """
    lines = text.splitlines()
    entries: list[TodoEntry] = []
    i = 0
    while i < len(lines):
        match = H2_TITLE.match(lines[i])
        if match is None:
            i += 1
            continue
        title = match.group("title").strip()
        body_start = i + 1
        end = _find_entry_end(lines, body_start)
        body_lines = lines[body_start:end]
        entries.append(_build_entry(path, title, i + 1, body_start + 1, body_lines))
        i = end
    return entries


def _find_entry_end(lines: list[str], start: int) -> int:
    """Return the line index where the current entry ends (exclusive).

    Stops at the next ``## `` heading or any line matching ``ENTRY_SPLIT``
    (a literal ``---`` separator).
    """
    for j in range(start, len(lines)):
        line = lines[j]
        if H2_TITLE.match(line) or ENTRY_SPLIT.match(line):
            return j
    return len(lines)


def _build_entry(
    path: Path,
    title: str,
    title_line: int,
    body_first_line: int,
    body_lines: list[str],
) -> TodoEntry:
    """Assemble a TodoEntry from already-bounded body lines."""
    header_window = _header_window(body_lines)
    statuses = _collect_field(body_lines, header_window, body_first_line, "status")
    loggeds = _collect_field(body_lines, header_window, body_first_line, "logged")
    areas = _collect_field(body_lines, header_window, body_first_line, "area")
    body_text = "\n".join(body_lines[header_window:])
    status = statuses[0] if statuses else None
    logged = loggeds[0] if loggeds else None
    area = areas[0] if areas else None
    return TodoEntry(
        file_path=path,
        title=title,
        title_line=title_line,
        status_field=status,
        logged_field=logged,
        area_field=area,
        duplicate_status=len(statuses) > 1,
        duplicate_logged=len(loggeds) > 1,
        duplicate_area=len(areas) > 1,
        header_in_order=_in_order(status, logged, area),
        body=body_text,
    )


def _header_window(body_lines: list[str]) -> int:
    """Return the index where the header zone ends (exclusive).

    The header zone runs from body start to the first non-blank line
    that is NOT a recognised ``**Status:**`` / ``**Logged:**`` /
    ``**Area:**`` label.
    """
    for idx, line in enumerate(body_lines):
        if not line.strip():
            continue
        if LABEL_STATUS.match(line) or LABEL_LOGGED.match(line) or LABEL_AREA.match(line):
            continue
        return idx
    return len(body_lines)


def _collect_field(
    body_lines: list[str], window_end: int, body_first_line: int, kind: str
) -> list[FieldRecord]:
    """Return every match of ``kind`` (status|logged|area) in the window."""
    label = {"status": LABEL_STATUS, "logged": LABEL_LOGGED, "area": LABEL_AREA}[kind]
    out: list[FieldRecord] = []
    for offset in range(window_end):
        m = label.match(body_lines[offset])
        if m is None:
            continue
        raw = m.group("value")
        out.append(
            FieldRecord(
                line_number=body_first_line + offset,
                raw_value=raw,
                value_valid=_is_valid_value(kind, raw),
            )
        )
    return out


def _is_valid_value(kind: str, raw: str) -> bool:
    if kind == "status":
        return raw in STATUS_VALUES
    if kind == "logged":
        if raw == "unknown":
            return True
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return False
        try:
            date.fromisoformat(raw)
        except ValueError:
            return False
        return True
    return True  # Area accepts any value, including empty


def _in_order(
    status: FieldRecord | None,
    logged: FieldRecord | None,
    area: FieldRecord | None,
) -> bool:
    """All three present and Status < Logged < Area by line number."""
    if status is None or logged is None or area is None:
        return False
    return status.line_number < logged.line_number < area.line_number  # noqa: E501


__all__ = [
    "AREA_LINE",
    "ENTRY_SPLIT",
    "FieldRecord",
    "H2_TITLE",
    "LABEL_AREA",
    "LABEL_LOGGED",
    "LABEL_STATUS",
    "LOGGED_LINE",
    "SKIP_DIR_NAMES",
    "STATUS_LINE",
    "STATUS_VALUES",
    "TodoEntry",
    "discover_todo_files",
    "parse_file",
    "parse_text",
]
