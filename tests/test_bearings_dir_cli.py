"""CLI wiring tests for `bearings here` and `bearings pending`.

The underlying helpers are covered elsewhere — here we're checking
that argparse routes properly and exit codes / stderr messages are
sane."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bearings.bearings_dir.io import (
    MANIFEST_FILE,
    PENDING_FILE,
    STATE_FILE,
    bearings_path,
)
from bearings.cli import main


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("# demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def test_cli_here_init_writes_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _init_git_repo(tmp_path)
    rc = main(["here", "init", "--dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Wrote .bearings/" in out
    root = bearings_path(tmp_path.resolve())
    assert (root / MANIFEST_FILE).exists()
    assert (root / STATE_FILE).exists()
    assert (root / PENDING_FILE).exists()


def test_cli_here_check_requires_init(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["here", "check", "--dir", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "run `bearings here init`" in err


def test_cli_here_check_succeeds_after_init(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    assert main(["here", "init", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()  # drain init output
    rc = main(["here", "check", "--dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "last_validated" in out


def test_cli_pending_add_then_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(
        [
            "pending",
            "add",
            "run-migration",
            "--description",
            "apply 0017",
            "--dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    capsys.readouterr()
    assert main(["pending", "list", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "run-migration" in out
    assert "apply 0017" in out


def test_cli_pending_resolve_known_and_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["pending", "add", "alpha", "--dir", str(tmp_path)])
    capsys.readouterr()
    assert main(["pending", "resolve", "alpha", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()
    rc = main(["pending", "resolve", "never-added", "--dir", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "No pending op" in err


def test_cli_pending_list_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["pending", "list", "--dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no pending operations" in out
