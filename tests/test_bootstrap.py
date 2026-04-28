"""Smoke tests proving the scaffolding actually imports and the CLI runs.

These are the minimum tests that justify wiring pytest in item 0.1 — they
exercise the package's ``__init__`` and the console-script entry point so
that subsequent items inherit a green baseline rather than a never-run
test suite.
"""

from __future__ import annotations

import pytest

import bearings
from bearings.cli import main


def test_package_exposes_version() -> None:
    """``bearings.__version__`` must be a non-empty PEP 440 dev string."""
    assert bearings.__version__
    assert "dev" in bearings.__version__


def test_cli_entry_point_runs_clean(capsys: pytest.CaptureFixture[str]) -> None:
    """Calling ``main()`` exits 0 and prints a one-line bootstrap notice."""
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "bearings v" in captured.out
    assert bearings.__version__ in captured.out
