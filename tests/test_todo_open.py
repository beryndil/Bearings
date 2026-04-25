"""``bearings todo open`` per spec §2.4."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bearings.todo.open import run_open

CONTENT = """\
# proj — Open Tasks

---

## newer entry

**Status:** Open
**Logged:** 2026-04-20
**Area:** db

Recent body.

---

## older entry

**Status:** In Progress
**Logged:** 2026-03-01
**Area:** ops

Older body that should sort first.

---

## blocked entry

**Status:** Blocked
**Logged:** 2026-04-15
**Area:** db

Blocked body.
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "TODO.md").write_text(CONTENT)
    return tmp_path


def test_default_status_filter_excludes_blocked(workspace: Path, capsys) -> None:
    rc = run_open(workspace)
    out = capsys.readouterr().out
    assert rc == 0
    assert "older entry" in out
    assert "newer entry" in out
    assert "blocked entry" not in out


def test_status_any_includes_all_three(workspace: Path, capsys) -> None:
    run_open(workspace, status="any")
    out = capsys.readouterr().out
    assert "blocked entry" in out
    assert "older entry" in out
    assert "newer entry" in out


def test_status_filter_specific_value(workspace: Path, capsys) -> None:
    run_open(workspace, status="Blocked")
    out = capsys.readouterr().out
    assert "blocked entry" in out
    assert "newer entry" not in out


def test_area_substring_filter(workspace: Path, capsys) -> None:
    run_open(workspace, status="any", area="db")
    out = capsys.readouterr().out
    assert "newer entry" in out
    assert "blocked entry" in out
    assert "older entry" not in out


def test_sort_order_oldest_logged_first(workspace: Path, capsys) -> None:
    run_open(workspace)
    out = capsys.readouterr().out
    older_pos = out.find("older entry")
    newer_pos = out.find("newer entry")
    assert 0 <= older_pos < newer_pos


def test_json_format_returns_array(workspace: Path, capsys) -> None:
    run_open(workspace, status="any", output_format="json")
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert {p["title"] for p in payload} == {
        "newer entry",
        "older entry",
        "blocked entry",
    }
    record = next(p for p in payload if p["title"] == "newer entry")
    assert record["status"] == "Open"
    assert record["logged"] == "2026-04-20"
    assert record["area"] == "db"


def test_empty_workspace_emits_nothing(tmp_path: Path, capsys) -> None:
    rc = run_open(tmp_path)
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_open_returns_zero_even_with_findings(tmp_path: Path) -> None:
    (tmp_path / "TODO.md").write_text("## bad\n\nno header\n")
    assert run_open(tmp_path) == 0  # spec §2.4: exit 0 always
