"""Tests for the ``bearings pending`` subcommand.

Acceptance-criteria coverage:

* AC-cp-1  ``pending add`` writes a row to pending.toml and prints
  ``Pending: <name> (started <iso8601>)``.
* AC-cp-2  ``pending resolve`` removes the row and prints ``Resolved: <name>``.
* AC-cp-3  ``pending list`` prints rows oldest-first.
* AC-cp-4  ``pending list`` prints ``(no pending operations)`` when empty.
* AC-cp-5  ``pending resolve`` on unknown name prints to stderr and exits 1.
* AC-cp-6  ``pending add`` with --description stores the value and list shows it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from bearings.cli.app import main
from bearings.config.constants import (
    BEARINGS_DIR_PENDING_FILENAME,
    BEARINGS_DIR_SUBDIR,
    CLI_EXIT_OK,
    CLI_EXIT_OPERATION_FAILURE,
)


def _pending_path(root: Path) -> Path:
    """Return (and ensure) the pending.toml path under root/.bearings/."""
    p = root / BEARINGS_DIR_SUBDIR / BEARINGS_DIR_PENDING_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_ops(root: Path) -> dict[str, object]:
    path = root / BEARINGS_DIR_SUBDIR / BEARINGS_DIR_PENDING_FILENAME
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return dict(data.get("ops", {}))


# ---------------------------------------------------------------------------
# AC-cp-1  pending add — writes row and prints Pending: line
# ---------------------------------------------------------------------------


def test_pending_add_writes_row(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _pending_path(tmp_path)  # ensure .bearings/ exists
    rc = main(["pending", "add", "deploy", "--dir", str(tmp_path)])
    assert rc == CLI_EXIT_OK
    ops = _load_ops(tmp_path)
    assert "deploy" in ops


def test_pending_add_prints_pending_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _pending_path(tmp_path)
    rc = main(["pending", "add", "my-op", "--dir", str(tmp_path)])
    assert rc == CLI_EXIT_OK
    out = capsys.readouterr().out
    assert out.startswith("Pending: my-op (started ")
    assert out.endswith(")\n")


def test_pending_add_stores_started_at(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _pending_path(tmp_path)
    main(["pending", "add", "my-op", "--dir", str(tmp_path)])
    ops = _load_ops(tmp_path)
    assert "started_at" in ops["my-op"]  # type: ignore[operator]


# ---------------------------------------------------------------------------
# AC-cp-6  pending add --description stores value; list shows it
# ---------------------------------------------------------------------------


def test_pending_add_with_description(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _pending_path(tmp_path)
    rc = main(
        ["pending", "add", "build", "--description", "Build the release", "--dir", str(tmp_path)]
    )
    assert rc == CLI_EXIT_OK
    ops = _load_ops(tmp_path)
    assert ops["build"]["description"] == "Build the release"  # type: ignore[index]


# ---------------------------------------------------------------------------
# AC-cp-2  pending resolve — removes row and prints Resolved: line
# ---------------------------------------------------------------------------


def test_pending_resolve_removes_row(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _pending_path(tmp_path)
    main(["pending", "add", "deploy", "--dir", str(tmp_path)])
    capsys.readouterr()  # clear add output
    rc = main(["pending", "resolve", "deploy", "--dir", str(tmp_path)])
    assert rc == CLI_EXIT_OK
    ops = _load_ops(tmp_path)
    assert "deploy" not in ops


def test_pending_resolve_prints_resolved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _pending_path(tmp_path)
    main(["pending", "add", "deploy", "--dir", str(tmp_path)])
    capsys.readouterr()
    main(["pending", "resolve", "deploy", "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert out == "Resolved: deploy\n"


# ---------------------------------------------------------------------------
# AC-cp-5  pending resolve unknown name — stderr + exit 1
# ---------------------------------------------------------------------------


def test_pending_resolve_unknown_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _pending_path(tmp_path)
    rc = main(["pending", "resolve", "nonexistent", "--dir", str(tmp_path)])
    assert rc == CLI_EXIT_OPERATION_FAILURE
    err = capsys.readouterr().err
    assert "nonexistent" in err


def test_pending_resolve_unknown_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _pending_path(tmp_path)
    main(["pending", "resolve", "ghost", "--dir", str(tmp_path)])
    err = capsys.readouterr().err
    assert err == "No pending op named 'ghost'.\n"


# ---------------------------------------------------------------------------
# AC-cp-3  pending list — rows oldest-first
# ---------------------------------------------------------------------------


def test_pending_list_oldest_first(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Write two ops manually with known timestamps so order is deterministic.
    pending_path = _pending_path(tmp_path)
    pending_path.write_text(
        "[ops.newer]\n"
        'started_at = "2024-01-02T00:00:00Z"\n'
        'description = "second"\n'
        "\n"
        "[ops.older]\n"
        'started_at = "2024-01-01T00:00:00Z"\n'
        'description = "first"\n',
        encoding="utf-8",
    )
    rc = main(["pending", "list", "--dir", str(tmp_path)])
    assert rc == CLI_EXIT_OK
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln]
    assert len(lines) == 2
    # older op must come first
    assert "older" in lines[0]
    assert "newer" in lines[1]


def test_pending_list_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pending_path = _pending_path(tmp_path)
    pending_path.write_text(
        '[ops.task]\nstarted_at = "2024-03-01T09:00:00Z"\ndescription = "do the thing"\n',
        encoding="utf-8",
    )
    main(["pending", "list", "--dir", str(tmp_path)])
    out = capsys.readouterr().out.strip()
    assert out == "2024-03-01T09:00:00Z  task — do the thing"


# ---------------------------------------------------------------------------
# AC-cp-4  pending list — empty → (no pending operations)
# ---------------------------------------------------------------------------


def test_pending_list_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _pending_path(tmp_path)
    rc = main(["pending", "list", "--dir", str(tmp_path)])
    assert rc == CLI_EXIT_OK
    assert capsys.readouterr().out == "(no pending operations)\n"


def test_pending_list_absent_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # No .bearings/ dir at all — load_ops returns empty dict.
    rc = main(["pending", "list", "--dir", str(tmp_path)])
    assert rc == CLI_EXIT_OK
    assert capsys.readouterr().out == "(no pending operations)\n"
