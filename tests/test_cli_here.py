"""Tests for the ``bearings here`` subcommand.

Acceptance-criteria coverage:

* AC-here-1  ``here init`` creates .bearings/{manifest,state,pending}.toml.
* AC-here-2  ``here init`` prints ``Wrote .bearings/ to <root>``.
* AC-here-3  ``here init`` exits 0.
* AC-here-4  ``here init`` is idempotent (second run exits 0, files intact).
* AC-here-5  ``here check`` exits 1 when .bearings/ is missing.
* AC-here-6  ``here check`` exits 1 stderr contains FileNotFoundError message.
* AC-here-7  ``here check`` exits 0 when .bearings/ exists.
* AC-here-8  ``here check`` stdout contains ``Revalidated <path>:``.
* AC-here-9  ``here check`` stdout contains ``last_validated = <iso8601>``.
* AC-here-10 ``here check`` updates state.toml with last_validated.
* AC-here-11 ``here check`` stdout contains an environment note line.
* AC-here-12 ``here check`` branch/clean state in revalidation line.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from bearings.cli.app import main
from bearings.cli.here import _parse_git_summary
from bearings.config.constants import (
    BEARINGS_DIR_MANIFEST_FILENAME,
    BEARINGS_DIR_PENDING_FILENAME,
    BEARINGS_DIR_STATE_FILENAME,
    BEARINGS_DIR_SUBDIR,
    CLI_EXIT_OK,
    CLI_EXIT_OPERATION_FAILURE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bdir(root: Path) -> Path:
    return root / BEARINGS_DIR_SUBDIR


def _manifest(root: Path) -> Path:
    return _bdir(root) / BEARINGS_DIR_MANIFEST_FILENAME


def _state(root: Path) -> Path:
    return _bdir(root) / BEARINGS_DIR_STATE_FILENAME


def _pending(root: Path) -> Path:
    return _bdir(root) / BEARINGS_DIR_PENDING_FILENAME


def _init(tmp_path: Path) -> int:
    """Run ``bearings here init`` on tmp_path."""
    return main(["here", "init", "--dir", str(tmp_path)])


# ---------------------------------------------------------------------------
# AC-here-1  init creates .bearings/ files
# ---------------------------------------------------------------------------


def test_here_init_creates_manifest(tmp_path: Path) -> None:
    _init(tmp_path)
    assert _manifest(tmp_path).exists()


def test_here_init_creates_state(tmp_path: Path) -> None:
    _init(tmp_path)
    assert _state(tmp_path).exists()


def test_here_init_creates_pending(tmp_path: Path) -> None:
    _init(tmp_path)
    assert _pending(tmp_path).exists()


# ---------------------------------------------------------------------------
# AC-here-2  init stdout
# ---------------------------------------------------------------------------


def test_here_init_stdout_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _init(tmp_path)
    out = capsys.readouterr().out
    assert f"Wrote .bearings/ to {tmp_path}" in out


# ---------------------------------------------------------------------------
# AC-here-3  init exit code
# ---------------------------------------------------------------------------


def test_here_init_exits_0(tmp_path: Path) -> None:
    rc = _init(tmp_path)
    assert rc == CLI_EXIT_OK


# ---------------------------------------------------------------------------
# AC-here-4  init idempotent
# ---------------------------------------------------------------------------


def test_here_init_idempotent(tmp_path: Path) -> None:
    _init(tmp_path)
    rc = _init(tmp_path)
    assert rc == CLI_EXIT_OK
    assert _manifest(tmp_path).exists()


# ---------------------------------------------------------------------------
# AC-here-5  check exits 1 when .bearings/ missing
# ---------------------------------------------------------------------------


def test_here_check_missing_bearings_dir_exits_1(tmp_path: Path) -> None:
    rc = main(["here", "check", "--dir", str(tmp_path)])
    assert rc == CLI_EXIT_OPERATION_FAILURE


# ---------------------------------------------------------------------------
# AC-here-6  check stderr contains FileNotFoundError when missing
# ---------------------------------------------------------------------------


def test_here_check_missing_stderr_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["here", "check", "--dir", str(tmp_path)])
    err = capsys.readouterr().err
    assert "FileNotFoundError" in err


# ---------------------------------------------------------------------------
# AC-here-7  check exits 0 when .bearings/ exists
# ---------------------------------------------------------------------------


def test_here_check_exits_0_when_initialized(tmp_path: Path) -> None:
    _init(tmp_path)
    rc = main(["here", "check", "--dir", str(tmp_path)])
    assert rc == CLI_EXIT_OK


# ---------------------------------------------------------------------------
# AC-here-8  check stdout contains Revalidated line
# ---------------------------------------------------------------------------


def test_here_check_stdout_revalidated(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _init(tmp_path)
    capsys.readouterr()  # clear init output
    main(["here", "check", "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert f"Revalidated {tmp_path}:" in out


# ---------------------------------------------------------------------------
# AC-here-9  check stdout contains last_validated
# ---------------------------------------------------------------------------


def test_here_check_stdout_last_validated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(tmp_path)
    capsys.readouterr()
    main(["here", "check", "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "last_validated = " in out


def test_here_check_last_validated_is_iso8601(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(tmp_path)
    capsys.readouterr()
    main(["here", "check", "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    # Find the last_validated line and check format: YYYY-MM-DDTHH:MM:SSZ
    line = next(ln for ln in out.splitlines() if ln.startswith("last_validated = "))
    ts = line.split("= ", 1)[1].strip()
    assert "T" in ts
    assert ts.endswith("Z")


# ---------------------------------------------------------------------------
# AC-here-10  check updates state.toml
# ---------------------------------------------------------------------------


def test_here_check_updates_state_toml(tmp_path: Path) -> None:
    _init(tmp_path)
    main(["here", "check", "--dir", str(tmp_path)])
    with _state(tmp_path).open("rb") as fh:
        data = tomllib.load(fh)
    assert "last_validated" in data


def test_here_check_last_validated_written_to_state(tmp_path: Path) -> None:
    _init(tmp_path)
    main(["here", "check", "--dir", str(tmp_path)])
    with _state(tmp_path).open("rb") as fh:
        data = tomllib.load(fh)
    lv = data["last_validated"]
    # Value is an ISO 8601 string (written as plain string, not native datetime)
    assert isinstance(lv, str)
    assert "T" in lv


# ---------------------------------------------------------------------------
# AC-here-11  check stdout contains environment note
# ---------------------------------------------------------------------------


def test_here_check_stdout_has_env_note(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _init(tmp_path)
    capsys.readouterr()
    main(["here", "check", "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln]
    # At least 3 lines: Revalidated, last_validated, env note
    assert len(lines) >= 3


# ---------------------------------------------------------------------------
# AC-here-12  check branch/state in revalidation line
# ---------------------------------------------------------------------------


def test_here_check_revalidated_line_has_git_info(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When git status returns a known format, branch+state appear in output."""
    monkeypatch.setattr(
        "bearings.cli.here.probe_git_status",
        lambda d: "clean, branch main, 0 changed, 0 stashes",
    )
    monkeypatch.setattr(
        "bearings.cli.here.probe_env_status",
        lambda d: "lockfile fresh.",
    )
    _init(tmp_path)
    capsys.readouterr()
    main(["here", "check", "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "branch main" in out
    assert "clean" in out


def test_here_check_non_git_repo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "bearings.cli.here.probe_git_status",
        lambda d: "not a git repo",
    )
    monkeypatch.setattr(
        "bearings.cli.here.probe_env_status",
        lambda d: "no lockfile detected.",
    )
    _init(tmp_path)
    capsys.readouterr()
    main(["here", "check", "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "not a git repo" in out


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


def test_parse_git_summary_clean() -> None:
    s = _parse_git_summary("clean, branch main, 0 changed, 0 stashes")
    assert s == "branch main, clean"


def test_parse_git_summary_dirty() -> None:
    s = _parse_git_summary("dirty, branch feature-x, 3 changed, 0 stashes")
    assert s == "branch feature-x, dirty"


def test_parse_git_summary_not_a_repo() -> None:
    s = _parse_git_summary("not a git repo")
    assert s == "not a git repo"
