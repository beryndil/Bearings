"""``bearings todo recent`` per spec §2.7.

Primary signal: ``git log -p`` on the TODO.md within the last N days.
For every commit touching the file, parse the file at parent vs. commit
and diff entries by title. Fallback when the file is not in a git repo:
filter by the entry's own ``Logged:`` date being within N days.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from bearings.todo.parse import TodoEntry, discover_todo_files, parse_file, parse_text

GIT_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class RecentRecord:
    path: Path
    entry: TodoEntry
    kind: str  # "added" | "modified"


def _find_git_root(path: Path) -> Path | None:
    """Walk upward looking for a .git directory."""
    for parent in [path, *path.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def _git(repo_root: Path, *args: str) -> tuple[int, str]:
    """Run a git subcommand. Returns (returncode, stdout). Failures
    return (-1, '') so the caller can fall back gracefully without
    leaking stack traces."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (subprocess.SubprocessError, OSError):
        return -1, ""
    return result.returncode, result.stdout


def _commits_touching(repo_root: Path, rel: Path, days: int) -> list[str]:
    """SHA list, newest first, of commits touching ``rel`` in the window."""
    rc, out = _git(
        repo_root,
        "log",
        f"--since={days}.days.ago",
        "--format=%H",
        "--",
        str(rel),
    )
    if rc != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _show_at(repo_root: Path, sha: str, rel: Path) -> str | None:
    """Return file contents at ``sha`` or None when the path didn't exist."""
    rc, out = _git(repo_root, "show", f"{sha}:{rel}")
    if rc != 0:
        return None
    return out


def _entries_by_title(text: str | None, file_path: Path) -> dict[str, TodoEntry]:
    if text is None:
        return {}
    return {entry.title: entry for entry in parse_text(file_path, text)}


def _classify_commit(
    repo_root: Path, sha: str, rel: Path, file_path: Path
) -> tuple[set[str], set[str]]:
    """Compare parent..sha for one commit. Returns (added, modified) titles."""
    after = _entries_by_title(_show_at(repo_root, sha, rel), file_path)
    before_text = _show_at(repo_root, f"{sha}^", rel)
    before = _entries_by_title(before_text, file_path)
    added: set[str] = set()
    modified: set[str] = set()
    for title, entry in after.items():
        prior = before.get(title)
        if prior is None:
            added.add(title)
        elif prior.body != entry.body:
            modified.add(title)
    return added, modified


def _git_recent_titles(file_path: Path, days: int) -> tuple[set[str], set[str]]:
    """Newest-commit-wins classification.

    ``git log`` returns commits in reverse chronological order, so the
    first commit that touches a given title decides whether that title
    reads as ``added`` or ``modified`` for the window. Without this,
    an entry added in commit N and edited in commit N+1 would always
    collapse to ``added`` — losing the more interesting "moved
    recently" signal that the hook injection is meant to surface.
    """
    repo_root = _find_git_root(file_path)
    if repo_root is None:
        return set(), set()
    try:
        rel = file_path.relative_to(repo_root)
    except ValueError:
        return set(), set()
    classification: dict[str, str] = {}
    for sha in _commits_touching(repo_root, rel, days):
        added, modified = _classify_commit(repo_root, sha, rel, file_path)
        for title in added:
            classification.setdefault(title, "added")
        for title in modified:
            classification.setdefault(title, "modified")
    added_set = {t for t, kind in classification.items() if kind == "added"}
    modified_set = {t for t, kind in classification.items() if kind == "modified"}
    return added_set, modified_set


def _records_from_git(file_path: Path, days: int) -> list[RecentRecord]:
    added, modified = _git_recent_titles(file_path, days)
    if not added and not modified:
        return []
    out: list[RecentRecord] = []
    for entry in parse_file(file_path):
        if entry.title in added:
            out.append(RecentRecord(path=file_path, entry=entry, kind="added"))
        elif entry.title in modified:
            out.append(RecentRecord(path=file_path, entry=entry, kind="modified"))
    return out


def _records_from_logged(file_path: Path, days: int, today: date) -> list[RecentRecord]:
    """Non-git fallback: filter by ``Logged:`` within window."""
    out: list[RecentRecord] = []
    for entry in parse_file(file_path):
        if entry.logged_date is None:
            continue
        if (today - entry.logged_date).days > days:
            continue
        out.append(RecentRecord(path=file_path, entry=entry, kind="modified"))
    return out


def _collect(root: Path, days: int, today: date) -> list[RecentRecord]:
    out: list[RecentRecord] = []
    for path in discover_todo_files(root):
        if _find_git_root(path) is not None:
            out.extend(_records_from_git(path, days))
        else:
            out.extend(_records_from_logged(path, days, today))
    return out


def _format_text(records: list[RecentRecord], root: Path) -> str:
    grouped: dict[Path, list[RecentRecord]] = {}
    for rec in records:
        grouped.setdefault(rec.path, []).append(rec)
    blocks: list[str] = []
    for path in sorted(grouped):
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        blocks.append(f"## {rel}")
        for rec in grouped[path]:
            e = rec.entry
            blocks.append(
                f"  [{rec.kind}] {e.title}  "
                f"(Status: {e.status or '?'}, Logged: {e.logged_raw or 'unknown'})"
            )
    return "\n".join(blocks)


def _format_json(records: list[RecentRecord], root: Path) -> str:
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
                "kind": rec.kind,
                "title": e.title,
                "status": e.status,
                "logged": e.logged_raw,
                "area": e.area,
            }
        )
    return json.dumps(out, indent=2)


def run_recent(
    root: Path,
    *,
    days: int = 7,
    output_format: str = "text",
    today: date | None = None,
) -> int:
    """Execute ``bearings todo recent``. Returns 0 always per spec §2.7."""
    today = today or date.today()
    records = _collect(root, days, today)
    if output_format == "json":
        print(_format_json(records, root))
    else:
        text = _format_text(records, root)
        if text:
            print(text)
    return 0


__all__ = ["RecentRecord", "run_recent"]
