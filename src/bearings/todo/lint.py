"""Lint rules + ``bearings todo check`` runner per spec §2.5.

Hard rules (E001-E008) always fail. Soft rules (W101 age, W102 shipped-
language) are advisory. Per spec §2.3 + §2.5 v1 does NOT distinguish
warning-only runs in the exit code — the PreToolUse git-commit hook
inspects the JSON finding set itself rather than relying on exit code
granularity.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from bearings.todo.parse import TodoEntry, discover_todo_files, parse_file

LEVEL_ERROR = "ERROR"
LEVEL_WARN = "WARN"

DEFAULT_MAX_AGE_DAYS = 60

# Spec §2.5 (3): shipped-looking words flagged inside Open entries.
SHIPPED_WORDS_RE = re.compile(
    r"\b(shipped|done|landed|merged|delivered|completed)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LintFinding:
    path: Path
    line: int
    level: str
    rule: str
    message: str
    title: str | None


def lint_entry(entry: TodoEntry, today: date, max_age_days: int) -> list[LintFinding]:
    """Apply per-entry rules E001-E007 + W101 + W102."""
    findings: list[LintFinding] = []
    findings.extend(_check_field_presence(entry))
    findings.extend(_check_field_values(entry))
    findings.extend(_check_field_duplicates(entry))
    findings.extend(_check_field_order(entry))
    findings.extend(_check_age_warning(entry, today, max_age_days))
    findings.extend(_check_shipped_language(entry))
    return findings


def _check_field_presence(entry: TodoEntry) -> list[LintFinding]:
    """E001/E002/E003 — each missing header field gets its own finding.

    When *all three* are missing, emit a single E008 instead, per spec
    §2.5 (4) "orphan-h2-no-header."
    """
    s = entry.status_field
    logged = entry.logged_field
    a = entry.area_field
    if s is None and logged is None and a is None:
        return [
            LintFinding(
                path=entry.file_path,
                line=entry.title_line,
                level=LEVEL_ERROR,
                rule="E008",
                message="H2 entry has no header triplet (Status/Logged/Area)",
                title=entry.title,
            )
        ]
    out: list[LintFinding] = []
    if s is None:
        out.append(_err(entry, entry.title_line, "E001", "Missing **Status:** header"))
    if logged is None:
        out.append(_err(entry, entry.title_line, "E002", "Missing **Logged:** header"))
    if a is None:
        out.append(_err(entry, entry.title_line, "E003", "Missing **Area:** header"))
    return out


def _check_field_values(entry: TodoEntry) -> list[LintFinding]:
    """E004 (status value) + E005 (logged date format)."""
    out: list[LintFinding] = []
    s = entry.status_field
    if s is not None and not s.value_valid:
        out.append(
            _err(
                entry,
                s.line_number,
                "E004",
                f"Status value {s.raw_value!r} not in {{Open, Blocked, In Progress}}",
            )
        )
    logged = entry.logged_field
    if logged is not None and not logged.value_valid:
        out.append(
            _err(
                entry,
                logged.line_number,
                "E005",
                f"Logged value {logged.raw_value!r} is not YYYY-MM-DD or 'unknown'",
            )
        )
    return out


def _check_field_duplicates(entry: TodoEntry) -> list[LintFinding]:
    out: list[LintFinding] = []
    if entry.duplicate_status and entry.status_field is not None:
        out.append(
            _err(entry, entry.status_field.line_number, "E006", "Duplicate **Status:** header")
        )
    if entry.duplicate_logged and entry.logged_field is not None:
        out.append(
            _err(entry, entry.logged_field.line_number, "E006", "Duplicate **Logged:** header")
        )
    if entry.duplicate_area and entry.area_field is not None:
        out.append(_err(entry, entry.area_field.line_number, "E006", "Duplicate **Area:** header"))
    return out


def _check_field_order(entry: TodoEntry) -> list[LintFinding]:
    """E007 — three fields present but not in Status → Logged → Area order."""
    s = entry.status_field
    logged = entry.logged_field
    a = entry.area_field
    if s is None or logged is None or a is None:
        return []
    if entry.header_in_order:
        return []
    return [
        _err(
            entry,
            entry.title_line,
            "E007",
            "Header lines out of order (must be Status, Logged, Area)",
        )
    ]


def _check_age_warning(entry: TodoEntry, today: date, max_age_days: int) -> list[LintFinding]:
    """W101 — Open entry whose Logged date is older than max_age_days."""
    if entry.status != "Open":
        return []
    logged = entry.logged_date
    if logged is None:
        return []
    age = (today - logged).days
    if age < max_age_days:
        return []
    line = entry.logged_field.line_number if entry.logged_field else entry.title_line
    return [
        LintFinding(
            path=entry.file_path,
            line=line,
            level=LEVEL_WARN,
            rule="W101",
            message=f"Open entry is {age} days old (>= {max_age_days})",
            title=entry.title,
        )
    ]


def _check_shipped_language(entry: TodoEntry) -> list[LintFinding]:
    """W102 — Open entry body contains a shipped-looking word."""
    if entry.status != "Open":
        return []
    match = SHIPPED_WORDS_RE.search(entry.body)
    if match is None:
        return []
    return [
        LintFinding(
            path=entry.file_path,
            line=entry.title_line,
            level=LEVEL_WARN,
            rule="W102",
            message=(
                f"Open entry body contains shipped-looking word "
                f"{match.group(0)!r}; consider closing or rephrasing"
            ),
            title=entry.title,
        )
    ]


def _err(entry: TodoEntry, line: int, rule: str, message: str) -> LintFinding:
    return LintFinding(
        path=entry.file_path,
        line=line,
        level=LEVEL_ERROR,
        rule=rule,
        message=message,
        title=entry.title,
    )


def collect_findings(
    root: Path, today: date, max_age_days: int
) -> tuple[list[LintFinding], int, int]:
    """Walk root, lint every entry, return (findings, entry_count, file_count)."""
    files = discover_todo_files(root)
    findings: list[LintFinding] = []
    entry_count = 0
    for path in files:
        entries = parse_file(path)
        entry_count += len(entries)
        for entry in entries:
            findings.extend(lint_entry(entry, today, max_age_days))
    return findings, entry_count, len(files)


def format_text(
    findings: list[LintFinding], entries: int, files: int, *, quiet: bool, root: Path
) -> str:
    """Render findings as ``<path>:<line>: <LEVEL> <rule> — <message>``."""
    lines: list[str] = []
    if not quiet:
        for f in findings:
            try:
                rel = f.path.relative_to(root)
            except ValueError:
                rel = f.path
            lines.append(f"{rel}:{f.line}: {f.level} {f.rule} — {f.message}")
    errors = sum(1 for f in findings if f.level == LEVEL_ERROR)
    warns = sum(1 for f in findings if f.level == LEVEL_WARN)
    lines.append(
        f"TODO.md check: {errors} errors, {warns} warnings ({entries} entries across {files} files)"
    )
    return "\n".join(lines)


def format_json(findings: list[LintFinding], root: Path) -> str:
    """Render findings as a JSON array per spec §2.5 'JSON output'."""
    out: list[dict[str, object]] = []
    for f in findings:
        record = asdict(f)
        try:
            record["path"] = str(f.path.relative_to(root))
        except ValueError:
            record["path"] = str(f.path)
        out.append(record)
    return json.dumps(out, indent=2)


def run_check(
    root: Path,
    *,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    output_format: str = "text",
    quiet: bool = False,
    today: date | None = None,
) -> int:
    """Execute ``bearings todo check``. Returns the spec §2.5 exit code."""
    today = today or date.today()
    findings, entries, files = collect_findings(root, today, max_age_days)
    if output_format == "json":
        print(format_json(findings, root))
    else:
        print(format_text(findings, entries, files, quiet=quiet, root=root))
    return 1 if findings else 0


__all__ = [
    "DEFAULT_MAX_AGE_DAYS",
    "LEVEL_ERROR",
    "LEVEL_WARN",
    "LintFinding",
    "collect_findings",
    "format_json",
    "format_text",
    "lint_entry",
    "run_check",
]
