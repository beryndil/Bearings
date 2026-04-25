"""TodoEntry parsing per spec §1.

Each test asserts one rule from §1.2-§1.3 directly so a future spec
revision flagging a divergence points at the offending case.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from bearings.todo.parse import (
    SKIP_DIR_NAMES,
    discover_todo_files,
    parse_text,
)

WELL_FORMED = """\
# project — Open Tasks

---

## first entry

**Status:** Open
**Logged:** 2026-04-22
**Area:** db

A short body about the first entry.

---

## second entry

**Status:** Blocked
**Logged:** 2026-04-10
**Area:**

Body for the blocked one.

---
"""


def _entries(text: str):
    return parse_text(Path("/virt/TODO.md"), text)


def test_parses_two_well_formed_entries() -> None:
    entries = _entries(WELL_FORMED)
    assert [e.title for e in entries] == ["first entry", "second entry"]
    e0 = entries[0]
    assert e0.status == "Open"
    assert e0.logged_raw == "2026-04-22"
    assert e0.logged_date == date(2026, 4, 22)
    assert e0.area == "db"
    assert "A short body about the first entry." in e0.body
    assert e0.header_in_order is True


def test_empty_area_is_valid() -> None:
    entries = _entries(WELL_FORMED)
    assert entries[1].area == ""


def test_unknown_logged_value_parses_but_yields_no_date() -> None:
    text = """## x\n\n**Status:** Open\n**Logged:** unknown\n**Area:**\n\nbody\n"""
    e = _entries(text)[0]
    assert e.logged_raw == "unknown"
    assert e.logged_date is None


def test_missing_all_three_header_lines_yields_orphan() -> None:
    text = """## orphan\n\nJust a paragraph with no header.\n"""
    e = _entries(text)[0]
    assert e.status_field is None
    assert e.logged_field is None
    assert e.area_field is None


def test_missing_one_header_line_keeps_others() -> None:
    text = "## partial\n\n**Status:** Open\n**Area:** ops\n\nbody\n"
    e = _entries(text)[0]
    assert e.status == "Open"
    assert e.logged_field is None
    assert e.area == "ops"


def test_invalid_status_value_records_field_but_marks_invalid() -> None:
    text = "## bad\n\n**Status:** Pending\n**Logged:** 2026-04-22\n**Area:**\n\nbody\n"
    e = _entries(text)[0]
    assert e.status_field is not None
    assert e.status_field.raw_value == "Pending"
    assert e.status_field.value_valid is False
    assert e.status is None  # property only returns valid values


def test_invalid_logged_format_marked_invalid() -> None:
    text = "## bad\n\n**Status:** Open\n**Logged:** 04/22/2026\n**Area:**\n\nbody\n"
    e = _entries(text)[0]
    assert e.logged_field is not None
    assert e.logged_field.value_valid is False
    assert e.logged_date is None


def test_logged_real_calendar_dates_only() -> None:
    text = "## bad\n\n**Status:** Open\n**Logged:** 2026-13-99\n**Area:**\n\n"
    e = _entries(text)[0]
    assert e.logged_field is not None
    assert e.logged_field.value_valid is False


def test_duplicate_status_flagged() -> None:
    text = (
        "## dup\n\n"
        "**Status:** Open\n"
        "**Status:** Blocked\n"
        "**Logged:** 2026-04-22\n"
        "**Area:**\n\nbody\n"
    )
    e = _entries(text)[0]
    assert e.duplicate_status is True


def test_header_out_of_order_detected() -> None:
    text = "## ooo\n\n**Logged:** 2026-04-22\n**Status:** Open\n**Area:**\n\nbody\n"
    e = _entries(text)[0]
    assert e.header_in_order is False


def test_split_at_horizontal_rule_separator() -> None:
    text = "## a\n\nbody-a\n\n---\n\n## b\n\nbody-b\n"
    titles = [e.title for e in _entries(text)]
    assert titles == ["a", "b"]


def test_entry_extends_to_next_h2_when_no_separator() -> None:
    text = "## a\n\nbody-a-line-1\nbody-a-line-2\n## b\n\nbody-b\n"
    entries = _entries(text)
    assert len(entries) == 2
    assert "body-a-line-1" in entries[0].body
    assert "body-a-line-2" in entries[0].body


def test_h1_and_leading_prose_ignored() -> None:
    text = (
        "# Project\n\nIntro prose.\n\n---\n\n"
        "## first\n\n**Status:** Open\n**Logged:** 2026-04-22\n**Area:**\n\n"
    )
    entries = _entries(text)
    assert [e.title for e in entries] == ["first"]


def test_discover_skips_archive_filenames(tmp_path: Path) -> None:
    (tmp_path / "TODO.md").write_text("# x\n")
    (tmp_path / "TODO-archive-2026-04-22.md").write_text("# y\n")
    (tmp_path / "TODO.md.bak").write_text("# z\n")
    files = discover_todo_files(tmp_path)
    assert files == [tmp_path / "TODO.md"]


def test_discover_skips_listed_directories(tmp_path: Path) -> None:
    (tmp_path / "TODO.md").write_text("# root\n")
    for d in (".git", "node_modules", "_archive", ".venv"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "TODO.md").write_text("# nested\n")
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "TODO.md").write_text("# src\n")
    files = discover_todo_files(tmp_path)
    assert sorted(files) == sorted([tmp_path / "TODO.md", sub / "TODO.md"])


def test_skip_dir_names_matches_spec() -> None:
    """Spec §2.2 lists exactly these names."""
    expected = {
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
    assert SKIP_DIR_NAMES == expected
