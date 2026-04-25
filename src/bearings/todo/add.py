"""``bearings todo add`` per spec §2.6.

Appends a properly-formatted stub entry to a TODO.md, creating the file
with an H1 stub when missing. Hooks and Claude both use this command
rather than hand-writing entries — that's how schema conformance gets
guaranteed across actors.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from bearings.todo.parse import STATUS_VALUES

VALID_STATUS_VALUES: tuple[str, ...] = STATUS_VALUES


def _validate_status(status: str) -> str | None:
    """Return an error message when ``status`` is not a canonical value."""
    if status in VALID_STATUS_VALUES:
        return None
    return f"Invalid --status {status!r}; must be one of {', '.join(VALID_STATUS_VALUES)}"


def _render_entry(title: str, status: str, logged: str, area: str, body: str) -> str:
    """Render exactly the §1.2 three-line header + body."""
    parts = [
        f"## {title}",
        "",
        f"**Status:** {status}",
        f"**Logged:** {logged}",
        f"**Area:** {area}",
        "",
    ]
    if body:
        parts.append(body)
        parts.append("")
    return "\n".join(parts)


def _initial_file_stub(target: Path) -> str:
    """Header for a brand-new TODO.md."""
    parent_name = target.resolve().parent.name or "project"
    return f"# {parent_name} — Open Tasks\n\n"


def _append_block(existing: str, entry_text: str) -> str:
    """Glue a new entry onto existing content with proper ``---`` framing.

    Spec §2.6 calls for a separator before the new entry (skipped when
    the file is empty or already ends with one) and a trailing ``---``
    so the next append round-trips cleanly.
    """
    if not existing:
        return entry_text + "\n---\n"
    body = existing.rstrip("\n")
    needs_leading_separator = not body.endswith("---")
    leading = "\n\n---\n\n" if needs_leading_separator else "\n\n"
    return body + leading + entry_text + "\n---\n"


def run_add(
    root: Path,
    *,
    title: str,
    status: str = "Open",
    area: str = "",
    body: str = "",
    file: Path | None = None,
    today: date | None = None,
) -> int:
    """Execute ``bearings todo add``. Returns 0 on success, 2 on usage error."""
    msg = _validate_status(status)
    if msg is not None:
        print(msg, file=sys.stderr)
        return 2
    target = file if file is not None else (root / "TODO.md")
    logged = (today or date.today()).isoformat()
    entry_text = _render_entry(title, status, logged, area, body)
    try:
        if target.exists():
            existing = target.read_text(encoding="utf-8")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            existing = _initial_file_stub(target)
        target.write_text(_append_block(existing, entry_text), encoding="utf-8")
    except OSError as exc:
        print(f"bearings todo add: write failed: {exc}", file=sys.stderr)
        return 2
    try:
        rel = target.relative_to(root)
    except ValueError:
        rel = target
    print(f"Appended to {rel}: {title}")
    return 0


__all__ = ["VALID_STATUS_VALUES", "run_add"]
