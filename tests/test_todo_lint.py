"""Lint rule coverage per spec §2.5.

One test per rule id (E001-E008, W101, W102), plus run_check exit-code
behavior, plus a `quiet`/format=json round trip.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from bearings.todo.lint import (
    LEVEL_ERROR,
    LEVEL_WARN,
    lint_entry,
    run_check,
)
from bearings.todo.parse import parse_text

TODAY = date(2026, 4, 25)


def _lint(text: str, *, max_age_days: int = 60, today: date = TODAY):
    entries = parse_text(Path("/virt/TODO.md"), text)
    out = []
    for e in entries:
        out.extend(lint_entry(e, today, max_age_days))
    return out


def test_e001_missing_status() -> None:
    text = "## x\n\n**Logged:** 2026-04-22\n**Area:**\n\nbody\n"
    findings = _lint(text)
    assert any(f.rule == "E001" and f.level == LEVEL_ERROR for f in findings)


def test_e002_missing_logged() -> None:
    text = "## x\n\n**Status:** Open\n**Area:**\n\nbody\n"
    findings = _lint(text)
    assert any(f.rule == "E002" for f in findings)


def test_e003_missing_area() -> None:
    text = "## x\n\n**Status:** Open\n**Logged:** 2026-04-22\n\nbody\n"
    findings = _lint(text)
    assert any(f.rule == "E003" for f in findings)


def test_e004_invalid_status_value() -> None:
    text = "## x\n\n**Status:** Pending\n**Logged:** 2026-04-22\n**Area:**\n"
    findings = _lint(text)
    assert any(f.rule == "E004" for f in findings)


def test_e005_invalid_logged_format() -> None:
    text = "## x\n\n**Status:** Open\n**Logged:** 04/22/2026\n**Area:**\n"
    findings = _lint(text)
    assert any(f.rule == "E005" for f in findings)


def test_e006_duplicate_field() -> None:
    text = "## x\n\n**Status:** Open\n**Status:** Blocked\n**Logged:** 2026-04-22\n**Area:**\n"
    findings = _lint(text)
    assert any(f.rule == "E006" for f in findings)


def test_e007_header_out_of_order() -> None:
    text = "## x\n\n**Logged:** 2026-04-22\n**Status:** Open\n**Area:**\n"
    findings = _lint(text)
    assert any(f.rule == "E007" for f in findings)


def test_e008_orphan_h2_no_header() -> None:
    text = "## x\n\nJust prose. No header at all.\n"
    findings = _lint(text)
    e008 = [f for f in findings if f.rule == "E008"]
    assert len(e008) == 1
    # E008 should NOT also emit E001/E002/E003 (single consolidated finding)
    assert not any(f.rule in {"E001", "E002", "E003"} for f in findings)


def test_w101_age_warning_at_threshold() -> None:
    # Logged 70 days before today (>= 60-day default)
    old = TODAY.toordinal() - 70
    old_iso = date.fromordinal(old).isoformat()
    text = f"## old\n\n**Status:** Open\n**Logged:** {old_iso}\n**Area:**\n\nbody\n"
    findings = _lint(text)
    assert any(f.rule == "W101" and f.level == LEVEL_WARN for f in findings)


def test_w101_does_not_fire_under_threshold() -> None:
    recent_iso = date.fromordinal(TODAY.toordinal() - 10).isoformat()
    text = f"## fresh\n\n**Status:** Open\n**Logged:** {recent_iso}\n**Area:**\n\nbody\n"
    findings = _lint(text)
    assert not any(f.rule == "W101" for f in findings)


def test_w101_skips_blocked_entries() -> None:
    """Spec §2.5 (2): age applies to Status: Open only."""
    old_iso = date.fromordinal(TODAY.toordinal() - 200).isoformat()
    text = f"## blocked\n\n**Status:** Blocked\n**Logged:** {old_iso}\n**Area:**\n\nbody\n"
    findings = _lint(text)
    assert not any(f.rule == "W101" for f in findings)


def test_w102_shipped_language_in_open_entry() -> None:
    text = (
        "## x\n\n"
        "**Status:** Open\n"
        "**Logged:** 2026-04-22\n"
        "**Area:**\n\n"
        "Already shipped this last week.\n"
    )
    findings = _lint(text)
    assert any(f.rule == "W102" for f in findings)


def test_w102_skips_blocked_entries() -> None:
    text = (
        "## x\n\n**Status:** Blocked\n**Logged:** 2026-04-22\n**Area:**\n\nWas shipped already.\n"
    )
    findings = _lint(text)
    assert not any(f.rule == "W102" for f in findings)


def test_run_check_clean_exit_zero(tmp_path: Path, capsys) -> None:
    todo = tmp_path / "TODO.md"
    todo.write_text(
        "# x\n\n---\n\n## clean\n\n**Status:** Open\n**Logged:** 2026-04-22\n**Area:**\n\nbody\n"
    )
    rc = run_check(tmp_path, today=TODAY)
    captured = capsys.readouterr()
    assert rc == 0
    assert "0 errors, 0 warnings" in captured.out


def test_run_check_returns_one_on_any_finding(tmp_path: Path, capsys) -> None:
    todo = tmp_path / "TODO.md"
    todo.write_text("## bad\n\nno header\n")
    rc = run_check(tmp_path, today=TODAY)
    captured = capsys.readouterr()
    assert rc == 1
    assert "E008" in captured.out


def test_run_check_quiet_suppresses_findings_keeps_summary(tmp_path: Path, capsys) -> None:
    todo = tmp_path / "TODO.md"
    todo.write_text("## bad\n\nno header\n")
    run_check(tmp_path, quiet=True, today=TODAY)
    captured = capsys.readouterr()
    assert "E008" not in captured.out
    assert "1 errors" in captured.out


def test_run_check_json_format(tmp_path: Path, capsys) -> None:
    todo = tmp_path / "TODO.md"
    todo.write_text("## bad\n\nno header\n")
    run_check(tmp_path, output_format="json", today=TODAY)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert isinstance(payload, list)
    assert payload[0]["rule"] == "E008"
    assert payload[0]["title"] == "bad"


def test_run_check_uses_max_age_days_argument(tmp_path: Path) -> None:
    todo = tmp_path / "TODO.md"
    old_iso = date.fromordinal(TODAY.toordinal() - 30).isoformat()
    todo.write_text(f"## x\n\n**Status:** Open\n**Logged:** {old_iso}\n**Area:**\n\nbody\n")
    # default 60: clean. tightened 7: warning fires.
    assert run_check(tmp_path, today=TODAY) == 0
    assert run_check(tmp_path, max_age_days=7, today=TODAY) == 1
