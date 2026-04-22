"""Tests for pending-operations CRUD.

Key contracts:
  - `add` is idempotent on name and preserves `started` across
    re-notices (30-day stale flag depends on this).
  - `resolve` returns the removed op, or None for unknown names.
  - `list_ops` yields operations oldest-first.
"""

from __future__ import annotations

import time
from pathlib import Path

from bearings.bearings_dir import pending as pending_ops


def test_add_then_list(tmp_path: Path) -> None:
    pending_ops.add(tmp_path, "run-migration", description="apply 0017")
    ops = pending_ops.list_ops(tmp_path)
    assert len(ops) == 1
    assert ops[0].name == "run-migration"
    assert ops[0].description == "apply 0017"


def test_add_is_idempotent_on_name_and_preserves_started(tmp_path: Path) -> None:
    first = pending_ops.add(tmp_path, "fix-lockfile")
    time.sleep(0.01)  # ensure wall clock would have moved
    second = pending_ops.add(tmp_path, "fix-lockfile", description="re-noticed from a new session")
    assert second.started == first.started, "re-adding must not reset start time"
    ops = pending_ops.list_ops(tmp_path)
    assert len(ops) == 1
    assert ops[0].description == "re-noticed from a new session"


def test_resolve_removes_and_returns(tmp_path: Path) -> None:
    pending_ops.add(tmp_path, "a")
    pending_ops.add(tmp_path, "b")
    removed = pending_ops.resolve(tmp_path, "a")
    assert removed is not None and removed.name == "a"
    remaining = [op.name for op in pending_ops.list_ops(tmp_path)]
    assert remaining == ["b"]


def test_resolve_missing_name_returns_none(tmp_path: Path) -> None:
    assert pending_ops.resolve(tmp_path, "never-added") is None


def test_list_orders_oldest_first(tmp_path: Path) -> None:
    pending_ops.add(tmp_path, "first")
    time.sleep(0.01)
    pending_ops.add(tmp_path, "second")
    names = [op.name for op in pending_ops.list_ops(tmp_path)]
    assert names == ["first", "second"]


def test_get_matches_list_and_returns_none_for_missing(tmp_path: Path) -> None:
    pending_ops.add(tmp_path, "alpha")
    assert pending_ops.get(tmp_path, "alpha") is not None
    assert pending_ops.get(tmp_path, "beta") is None


def test_add_creates_bearings_dir_if_absent(tmp_path: Path) -> None:
    assert not (tmp_path / ".bearings").exists()
    pending_ops.add(tmp_path, "bootstrap")
    assert (tmp_path / ".bearings").is_dir()
    assert (tmp_path / ".bearings" / "pending.toml").is_file()
