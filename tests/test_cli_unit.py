"""Unit tests for the bearings CLI root parser + dispatch.

Exit codes per ``docs/behavior/bearings-cli.md`` §"Common observable
conventions":

* 0 — success.
* 1 — operation-level failure.
* 2 — usage / validation error.
"""

from __future__ import annotations

import pytest

from bearings.cli.app import main
from bearings.config.constants import (
    CLI_EXIT_OK,
    CLI_EXIT_USAGE_ERROR,
)


def test_bare_invocation_prints_bootstrap_and_exits_0(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main([])
    out = capsys.readouterr()
    assert rc == CLI_EXIT_OK
    assert "bearings v" in out.out


def test_version_flag_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--version"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_OK
    assert captured.out.startswith("bearings ")


def test_unknown_subcommand_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["bogus"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_USAGE_ERROR
    # argparse writes the error to stderr.
    assert captured.err


def test_help_flag_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--help"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_OK
    assert "usage:" in captured.out


def test_todo_with_no_subsubcommand_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["todo"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_USAGE_ERROR
    assert captured.err


def test_todo_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["todo", "--help"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_OK
    assert "open" in captured.out
    assert "check" in captured.out
    assert "add" in captured.out
    assert "recent" in captured.out


def test_todo_open_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["todo", "open", "--help"])
    captured = capsys.readouterr()
    assert rc == CLI_EXIT_OK
    assert "--status" in captured.out
    assert "--format" in captured.out
