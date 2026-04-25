"""``bearings todo recent`` per spec §2.7.

Covers both the git-log primary path and the non-git Logged-date
fallback. Git tests use a real ephemeral repo via ``subprocess`` so the
parsing logic actually runs against ``git log -p`` output, not a mock.
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import pytest

from bearings.todo.recent import run_recent

TODAY = date(2026, 4, 25)


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    """Run a git command in ``repo`` with deterministic identity."""
    base_env = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    if env:
        base_env.update(env)
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**dict(__import__("os").environ), **base_env},
    )


def test_non_git_fallback_uses_logged_date(tmp_path: Path, capsys) -> None:
    recent_iso = date.fromordinal(TODAY.toordinal() - 3).isoformat()
    old_iso = date.fromordinal(TODAY.toordinal() - 30).isoformat()
    (tmp_path / "TODO.md").write_text(
        f"## fresh\n\n**Status:** Open\n**Logged:** {recent_iso}\n**Area:**\n\nbody\n\n"
        f"---\n\n## old\n\n**Status:** Open\n**Logged:** {old_iso}\n**Area:**\n\nbody\n"
    )
    rc = run_recent(tmp_path, days=7, today=TODAY)
    out = capsys.readouterr().out
    assert rc == 0
    assert "fresh" in out
    assert "old" not in out


def test_non_git_fallback_excludes_unknown_logged(tmp_path: Path, capsys) -> None:
    (tmp_path / "TODO.md").write_text(
        "## x\n\n**Status:** Open\n**Logged:** unknown\n**Area:**\n\nbody\n"
    )
    run_recent(tmp_path, days=7, today=TODAY)
    assert capsys.readouterr().out == ""


def test_git_path_marks_added_for_new_entries(tmp_path: Path, capsys) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "TODO.md").write_text(
        "## first\n\n**Status:** Open\n**Logged:** 2026-04-22\n**Area:**\n\nbody\n"
    )
    _git(tmp_path, "add", "TODO.md")
    _git(tmp_path, "commit", "-q", "-m", "add first")
    rc = run_recent(tmp_path, days=7, today=TODAY)
    out = capsys.readouterr().out
    assert rc == 0
    assert "[added]" in out
    assert "first" in out


def test_git_path_marks_modified_when_body_changes(tmp_path: Path, capsys) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    todo = tmp_path / "TODO.md"
    todo.write_text(
        "## stable\n\n**Status:** Open\n**Logged:** 2026-04-22\n**Area:**\n\noriginal\n"
    )
    _git(tmp_path, "add", "TODO.md")
    _git(tmp_path, "commit", "-q", "-m", "first")
    todo.write_text(
        "## stable\n\n**Status:** Open\n**Logged:** 2026-04-22\n**Area:**\n\nrewritten body\n"
    )
    _git(tmp_path, "commit", "-q", "-am", "edit body")
    run_recent(tmp_path, days=7, today=TODAY)
    out = capsys.readouterr().out
    assert "[modified]" in out
    assert "stable" in out


def test_git_path_skips_old_commits(tmp_path: Path, capsys) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "TODO.md").write_text(
        "## ancient\n\n**Status:** Open\n**Logged:** 2026-01-01\n**Area:**\n\nbody\n"
    )
    _git(tmp_path, "add", "TODO.md")
    # Commit dated 60 days ago — outside a 7-day window. Git wants a
    # full timestamp; bare YYYY-MM-DD is rejected on some versions.
    old_iso = date.fromordinal(TODAY.toordinal() - 60).isoformat()
    old_stamp = f"{old_iso}T12:00:00+0000"
    _git(
        tmp_path,
        "commit",
        "-q",
        "-m",
        "old",
        env={"GIT_AUTHOR_DATE": old_stamp, "GIT_COMMITTER_DATE": old_stamp},
    )
    run_recent(tmp_path, days=7, today=TODAY)
    out = capsys.readouterr().out
    assert "ancient" not in out


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_recent_returns_zero_on_both_formats(tmp_path: Path, fmt: str) -> None:
    (tmp_path / "TODO.md").write_text(
        "## x\n\n**Status:** Open\n**Logged:** 2026-04-22\n**Area:**\n\nbody\n"
    )
    assert run_recent(tmp_path, days=7, output_format=fmt, today=TODAY) == 0
