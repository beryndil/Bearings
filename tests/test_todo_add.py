"""``bearings todo add`` per spec §2.6."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from bearings.todo.add import run_add
from bearings.todo.parse import parse_file

TODAY = date(2026, 4, 25)


def test_creates_new_file_with_h1_stub(tmp_path: Path) -> None:
    rc = run_add(tmp_path, title="hello", today=TODAY)
    assert rc == 0
    target = tmp_path / "TODO.md"
    text = target.read_text()
    assert text.startswith(f"# {tmp_path.name} — Open Tasks")
    assert "## hello" in text
    assert "**Status:** Open" in text
    assert "**Logged:** 2026-04-25" in text
    assert "**Area:**" in text


def test_default_status_open(tmp_path: Path) -> None:
    run_add(tmp_path, title="x", today=TODAY)
    entry = parse_file(tmp_path / "TODO.md")[0]
    assert entry.status == "Open"


def test_invalid_status_returns_two(tmp_path: Path, capsys) -> None:
    rc = run_add(tmp_path, title="x", status="Pending", today=TODAY)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Pending" in err
    assert not (tmp_path / "TODO.md").exists()


def test_appended_entry_round_trips_through_parser(tmp_path: Path) -> None:
    run_add(tmp_path, title="first", today=TODAY)
    run_add(
        tmp_path,
        title="second",
        status="Blocked",
        area="ops",
        body="A specific body line.",
        today=TODAY,
    )
    entries = parse_file(tmp_path / "TODO.md")
    assert [e.title for e in entries] == ["first", "second"]
    assert entries[1].status == "Blocked"
    assert entries[1].area == "ops"
    assert "A specific body line." in entries[1].body


def test_appended_entry_passes_lint(tmp_path: Path) -> None:
    """The CLI's whole point is schema conformance — round-trip through
    the linter to prove no E00N findings on a fresh stub."""
    from bearings.todo.lint import lint_entry

    run_add(tmp_path, title="x", today=TODAY)
    entry = parse_file(tmp_path / "TODO.md")[0]
    findings = lint_entry(entry, TODAY, max_age_days=60)
    assert all(f.level == "WARN" for f in findings), findings


def test_explicit_file_target(tmp_path: Path) -> None:
    target = tmp_path / "subdir" / "OTHER.md"
    rc = run_add(tmp_path, title="x", file=target, today=TODAY)
    assert rc == 0
    assert target.is_file()


def test_separator_framing(tmp_path: Path) -> None:
    """Spec §2.6: trailing ``---`` after each append so the next call
    round-trips cleanly."""
    run_add(tmp_path, title="a", today=TODAY)
    run_add(tmp_path, title="b", today=TODAY)
    text = (tmp_path / "TODO.md").read_text()
    # exactly 2 H2 entries, exactly 2 separators between/after them
    assert text.count("\n## ") == 2
    assert text.count("\n---\n") >= 2
