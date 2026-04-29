"""Tests for the ``bearings todo`` subcommand."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from bearings.cli._todo_io import parse_todo_file, walk_todo_files
from bearings.cli.app import main
from bearings.config.constants import (
    CLI_EXIT_OK,
    CLI_EXIT_OPERATION_FAILURE,
    CLI_EXIT_USAGE_ERROR,
)

# --- _todo_io unit ---------------------------------------------------------


def test_walk_finds_root_todo(tmp_path: Path) -> None:
    todo = tmp_path / "TODO.md"
    todo.write_text("# TODO\n\n## A\n\nstatus: Open\n", encoding="utf-8")
    found = walk_todo_files(tmp_path)
    assert found == [todo.resolve()]


def test_walk_skips_hidden_dirs(tmp_path: Path) -> None:
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "TODO.md").write_text("# x", encoding="utf-8")
    (tmp_path / "TODO.md").write_text("# real\n\n## A\nstatus: Open\n", encoding="utf-8")
    found = walk_todo_files(tmp_path)
    assert all(".venv" not in p.parts for p in found)


def test_walk_finds_nested_todos(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "TODO.md").write_text("# a\n\n## A\nstatus: Open\n", encoding="utf-8")
    (tmp_path / "TODO.md").write_text("# root\n\n## R\nstatus: Open\n", encoding="utf-8")
    found = walk_todo_files(tmp_path)
    assert len(found) == 2


def test_parse_extracts_status_and_area(tmp_path: Path) -> None:
    todo = tmp_path / "TODO.md"
    todo.write_text(
        "# TODO\n\n## First entry\n\nstatus: In Progress\narea: tooling\n\nbody line one\n",
        encoding="utf-8",
    )
    entries = parse_todo_file(todo)
    assert len(entries) == 1
    e = entries[0]
    assert e.title == "First entry"
    assert e.status == "In Progress"
    assert e.area == "tooling"
    assert e.summary == "body line one"


def test_parse_default_status_open(tmp_path: Path) -> None:
    todo = tmp_path / "TODO.md"
    todo.write_text("# TODO\n\n## No meta\n\nbody\n", encoding="utf-8")
    entries = parse_todo_file(todo)
    assert entries[0].status == "Open"


def test_parse_multiple_entries(tmp_path: Path) -> None:
    todo = tmp_path / "TODO.md"
    todo.write_text(
        "# TODO\n\n## A\nstatus: Open\nbody1\n\n## B\nstatus: Blocked\nbody2\n",
        encoding="utf-8",
    )
    entries = parse_todo_file(todo)
    assert [e.title for e in entries] == ["A", "B"]
    assert [e.status for e in entries] == ["Open", "Blocked"]


# --- todo open ------------------------------------------------------------


def test_todo_open_prints_open_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "TODO.md").write_text(
        "# TODO\n\n## Open one\nstatus: Open\nbody\n\n## Done one\nstatus: Done\nbody\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "open"])
    out = capsys.readouterr().out
    assert rc == CLI_EXIT_OK
    assert "Open one" in out
    assert "Done one" not in out


def test_todo_open_status_any(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "TODO.md").write_text(
        "# TODO\n\n## Open\nstatus: Open\n\n## Done\nstatus: Done\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "open", "--status", "any"])
    out = capsys.readouterr().out
    assert rc == CLI_EXIT_OK
    assert "Done" in out and "Open" in out


def test_todo_open_json_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "TODO.md").write_text(
        "# TODO\n\n## E1\nstatus: Open\narea: foo\nfirst line\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "open", "--format", "json"])
    out = capsys.readouterr().out
    assert rc == CLI_EXIT_OK
    payload = json.loads(out)
    assert isinstance(payload, list)
    assert payload[0]["title"] == "E1"
    assert payload[0]["area"] == "foo"


def test_todo_open_empty_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "open"])
    out = capsys.readouterr().out
    assert rc == CLI_EXIT_OK
    assert "no matching" in out.lower()


# --- todo check -----------------------------------------------------------


def test_todo_check_clean_exits_0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "TODO.md").write_text("# TODO\n\n## fresh\nstatus: Open\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "check"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_OK
    assert "0 finding(s)" in captured.out


def test_todo_check_finds_unknown_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "TODO.md").write_text(
        "# TODO\n\n## bogus-status\nstatus: Maybe\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "check"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_OPERATION_FAILURE
    assert "Maybe" in captured.out
    assert "1 finding(s)" in captured.out


def test_todo_check_finds_stale_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    todo = tmp_path / "TODO.md"
    todo.write_text("# TODO\n\n## stale\nstatus: Open\n", encoding="utf-8")
    # Backdate mtime by 60 days so --max-age-days=30 flags it stale.
    long_ago = time.time() - 60 * 86400
    os.utime(todo, (long_ago, long_ago))
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "check", "--max-age-days", "30"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_OPERATION_FAILURE
    assert "stale" in captured.out


def test_todo_check_quiet_suppresses_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "TODO.md").write_text(
        "# TODO\n\n## bogus-status\nstatus: Maybe\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "check", "--quiet"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_OPERATION_FAILURE
    # Body line for the finding suppressed; summary still present.
    assert "Maybe" not in captured.out
    assert "finding(s)" in captured.out


def test_todo_check_negative_max_age_exits_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "check", "--max-age-days", "-1"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_USAGE_ERROR
    assert "must be" in captured.err.lower()


# --- todo add -------------------------------------------------------------


def test_todo_add_creates_file_and_appends(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "add", "First entry", "--area", "tooling"])
    assert rc == CLI_EXIT_OK
    out = capsys.readouterr().out
    assert "appended" in out
    body = (tmp_path / "TODO.md").read_text(encoding="utf-8")
    assert "## First entry" in body
    assert "status: Open" in body
    assert "area: tooling" in body


def test_todo_add_appends_to_existing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "TODO.md").write_text("# TODO\n\n## Pre-existing\nstatus: Open\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "add", "Second"])
    assert rc == CLI_EXIT_OK
    body = (tmp_path / "TODO.md").read_text(encoding="utf-8")
    assert "## Pre-existing" in body
    assert "## Second" in body


# --- todo recent ----------------------------------------------------------


def test_todo_recent_default_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "TODO.md").write_text("# TODO\n\n## fresh\nstatus: Open\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "recent"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_OK
    assert "fresh" in captured.out


def test_todo_recent_zero_days_exits_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "recent", "--days", "0"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_USAGE_ERROR
    assert "must be" in captured.err.lower()


def test_todo_recent_excludes_old_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    todo = tmp_path / "TODO.md"
    todo.write_text("# TODO\n\n## old\nstatus: Open\n", encoding="utf-8")
    long_ago = time.time() - 30 * 86400
    os.utime(todo, (long_ago, long_ago))
    monkeypatch.chdir(tmp_path)
    rc = main(["todo", "recent", "--days", "7"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_OK
    assert "no matching" in captured.out.lower()
