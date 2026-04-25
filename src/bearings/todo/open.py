"""``bearings todo open`` per spec §2.4.

Lists open/in-progress entries from every ``TODO.md`` in scope, sorted
by Logged date ascending (oldest first). Used both by Dave directly and
by the UserPromptSubmit hook on "what's next" queries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from bearings.todo.parse import TodoEntry, discover_todo_files, parse_file

DEFAULT_STATUSES: tuple[str, ...] = ("Open", "In Progress")
ALL_STATUSES: tuple[str, ...] = ("Open", "Blocked", "In Progress")
BODY_PREVIEW_CHARS = 200


@dataclass(frozen=True)
class OpenRecord:
    path: Path
    entry: TodoEntry


def _matches_status(entry: TodoEntry, statuses: set[str]) -> bool:
    """Status filter handles "any" by accepting ALL_STATUSES."""
    return entry.status is not None and entry.status in statuses


def _matches_area(entry: TodoEntry, needle: str) -> bool:
    if not needle:
        return True
    haystack = entry.area or ""
    return needle.lower() in haystack.lower()


def _logged_sort_key(record: OpenRecord) -> tuple[int, str, str, str]:
    """(unknown-bucket, ISO date or '~', path, title) — unknown sorts last."""
    d = record.entry.logged_date
    if d is None:
        return (1, "~", str(record.path), record.entry.title)
    return (0, d.isoformat(), str(record.path), record.entry.title)


def _collect(root: Path, statuses: set[str], area_filter: str) -> list[OpenRecord]:
    out: list[OpenRecord] = []
    for path in discover_todo_files(root):
        for entry in parse_file(path):
            if not _matches_status(entry, statuses):
                continue
            if not _matches_area(entry, area_filter):
                continue
            out.append(OpenRecord(path=path, entry=entry))
    out.sort(key=_logged_sort_key)
    return out


def _body_preview(body: str) -> str:
    """First ~200 chars of body with whitespace collapsed, ellipsised."""
    flat = " ".join(body.split())
    if len(flat) <= BODY_PREVIEW_CHARS:
        return flat
    return flat[: BODY_PREVIEW_CHARS - 1].rstrip() + "…"


def _format_text(records: list[OpenRecord], root: Path) -> str:
    blocks: list[str] = []
    for rec in records:
        e = rec.entry
        try:
            rel = rec.path.relative_to(root)
        except ValueError:
            rel = rec.path
        status = e.status or "?"
        logged = e.logged_raw or "unknown"
        area = e.area or ""
        blocks.append(
            f"{rel}:{e.title}\n"
            f"  Status: {status}   Logged: {logged}   Area: {area}\n"
            f"  {_body_preview(e.body)}"
        )
    return "\n\n---\n\n".join(blocks)


def _format_json(records: list[OpenRecord], root: Path) -> str:
    out: list[dict[str, object]] = []
    for rec in records:
        e = rec.entry
        try:
            rel = rec.path.relative_to(root)
        except ValueError:
            rel = rec.path
        out.append(
            {
                "path": str(rel),
                "title": e.title,
                "status": e.status,
                "logged": e.logged_raw,
                "area": e.area,
                "body": e.body,
            }
        )
    return json.dumps(out, indent=2)


def _resolve_statuses(raw: str) -> set[str]:
    """Parse ``--status=...`` argument. ``any`` expands to all three."""
    if raw == "any":
        return set(ALL_STATUSES)
    chunks = [s.strip() for s in raw.split(",") if s.strip()]
    return set(chunks)


def run_open(
    root: Path,
    *,
    status: str = "Open,In Progress",
    area: str = "",
    output_format: str = "text",
) -> int:
    """Execute ``bearings todo open``. Returns 0 always per spec §2.4."""
    statuses = _resolve_statuses(status)
    records = _collect(root, statuses, area)
    if output_format == "json":
        print(_format_json(records, root))
    else:
        text = _format_text(records, root)
        if text:
            print(text)
    return 0


__all__ = ["ALL_STATUSES", "DEFAULT_STATUSES", "run_open"]
