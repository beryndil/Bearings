"""End-to-end ``bearings todo …`` invocation through ``cli.main``.

Confirms the argparse wiring + dispatch path actually reaches each
runner with the right flags, so a future regression in ``cli.py`` /
``todo/__init__.py`` parser-registration shows up here, not in
production.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from bearings.cli import main


@contextmanager
def _chdir(target: Path) -> Iterator[None]:
    prev = Path.cwd()
    os.chdir(target)
    try:
        yield
    finally:
        os.chdir(prev)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "TODO.md").write_text(
        "# proj — Open Tasks\n\n---\n\n"
        "## ready\n\n**Status:** Open\n**Logged:** 2026-04-22\n**Area:**\n\nbody\n"
    )
    return tmp_path


def test_open_subcommand_prints_entries(workspace: Path, capsys) -> None:
    with _chdir(workspace):
        rc = main(["todo", "open"])
    assert rc == 0
    assert "ready" in capsys.readouterr().out


def test_check_subcommand_clean_returns_zero(workspace: Path, capsys) -> None:
    with _chdir(workspace):
        rc = main(["todo", "check"])
    assert rc == 0
    assert "0 errors" in capsys.readouterr().out


def test_check_subcommand_dirty_returns_one(tmp_path: Path, capsys) -> None:
    (tmp_path / "TODO.md").write_text("## bad\n\nno header\n")
    with _chdir(tmp_path):
        rc = main(["todo", "check"])
    assert rc == 1
    assert "E008" in capsys.readouterr().out


def test_add_subcommand_appends(tmp_path: Path) -> None:
    with _chdir(tmp_path):
        rc = main(["todo", "add", "new entry"])
    assert rc == 0
    assert "## new entry" in (tmp_path / "TODO.md").read_text()


def test_add_subcommand_with_flags(tmp_path: Path) -> None:
    with _chdir(tmp_path):
        main(["todo", "add", "x", "--status", "Blocked", "--area", "db", "--body", "B"])
    text = (tmp_path / "TODO.md").read_text()
    assert "**Status:** Blocked" in text
    assert "**Area:** db" in text
    assert "B" in text


def test_recent_subcommand_returns_zero(workspace: Path) -> None:
    with _chdir(workspace):
        assert main(["todo", "recent"]) == 0


def test_check_json_format_via_main(workspace: Path, capsys) -> None:
    with _chdir(workspace):
        main(["todo", "check", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload == []
