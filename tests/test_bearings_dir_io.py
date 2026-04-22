"""Tests for atomic TOML IO, history append, and corruption
quarantine semantics.

Covers:
  - round-trip for each model shape
  - concurrent writers don't interleave (flock on Unix)
  - corrupt TOML → quarantined + None
  - Pydantic validation failure → quarantined + None
  - atomic-write produces either old or new content on interrupt
  - history.jsonl append survives a corrupted single line
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import pytest
import tomli_w

from bearings.bearings_dir.io import (
    append_history,
    bearings_path,
    ensure_bearings_dir,
    read_history,
    read_toml_model,
    write_toml_model,
)
from bearings.bearings_dir.schema import (
    HistoryEntry,
    Manifest,
    Pending,
    PendingOperation,
    State,
)


def test_bearings_path_and_ensure(tmp_path: Path) -> None:
    root = ensure_bearings_dir(tmp_path)
    assert root == bearings_path(tmp_path)
    assert root.is_dir()
    assert (root / "checks").is_dir()
    # Idempotent.
    assert ensure_bearings_dir(tmp_path) == root


def test_manifest_round_trip(tmp_path: Path) -> None:
    ensure_bearings_dir(tmp_path)
    path = bearings_path(tmp_path) / "manifest.toml"
    m = Manifest(
        name="Bearings",
        path=str(tmp_path),
        description="localhost UI",
        git_remote="git@github.com:Beryndil/Bearings.git",
        language="python 3.12",
    )
    write_toml_model(path, m)
    loaded = read_toml_model(path, Manifest)
    assert loaded is not None
    assert loaded.name == "Bearings"
    assert loaded.git_remote == m.git_remote
    assert loaded.description == m.description


def test_state_round_trip_preserves_environment(tmp_path: Path) -> None:
    ensure_bearings_dir(tmp_path)
    path = bearings_path(tmp_path) / "state.toml"
    original = State(branch="main", dirty=False)
    original.environment.notes.append("lockfile fresh")
    write_toml_model(path, original)
    loaded = read_toml_model(path, State)
    assert loaded is not None
    assert loaded.branch == "main"
    assert loaded.dirty is False
    assert "lockfile fresh" in loaded.environment.notes


def test_pending_round_trip_with_operations(tmp_path: Path) -> None:
    ensure_bearings_dir(tmp_path)
    path = bearings_path(tmp_path) / "pending.toml"
    pending = Pending(
        operations=[
            PendingOperation(name="migrate-0017", description="run the new migration"),
            PendingOperation(name="fix-lockfile"),
        ]
    )
    write_toml_model(path, pending)
    loaded = read_toml_model(path, Pending)
    assert loaded is not None
    names = {op.name for op in loaded.operations}
    assert names == {"migrate-0017", "fix-lockfile"}


def test_read_missing_file_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "absent.toml"
    assert read_toml_model(path, Manifest) is None


def test_corrupt_toml_quarantined(tmp_path: Path) -> None:
    ensure_bearings_dir(tmp_path)
    path = bearings_path(tmp_path) / "manifest.toml"
    path.write_text("this is not = valid toml =\n[[[", encoding="utf-8")
    result = read_toml_model(path, Manifest)
    assert result is None
    # Original path was renamed aside.
    assert not path.exists()
    quarantined = list(bearings_path(tmp_path).glob("corrupted-*-manifest.toml"))
    assert len(quarantined) == 1


def test_validation_failure_quarantined(tmp_path: Path) -> None:
    ensure_bearings_dir(tmp_path)
    path = bearings_path(tmp_path) / "manifest.toml"
    # Valid TOML, but missing required fields for Manifest.
    path.write_bytes(tomli_w.dumps({"bogus": "yes"}).encode("utf-8"))
    result = read_toml_model(path, Manifest)
    assert result is None
    assert not path.exists()
    assert list(bearings_path(tmp_path).glob("corrupted-*-manifest.toml"))


@pytest.mark.skipif(sys.platform == "win32", reason="flock not available on Windows")
def test_concurrent_writers_do_not_interleave(tmp_path: Path) -> None:
    """Two threads rewriting the same `pending.toml` should both land
    a fully-formed file. The check: after both finish, the file still
    parses cleanly — no torn write."""
    ensure_bearings_dir(tmp_path)
    path = bearings_path(tmp_path) / "pending.toml"
    write_toml_model(path, Pending())

    def writer(name: str) -> None:
        for _ in range(20):
            pending = Pending(operations=[PendingOperation(name=name)])
            write_toml_model(path, pending)

    t1 = threading.Thread(target=writer, args=("alpha",))
    t2 = threading.Thread(target=writer, args=("beta",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    loaded = read_toml_model(path, Pending)
    assert loaded is not None
    assert len(loaded.operations) == 1
    assert loaded.operations[0].name in {"alpha", "beta"}


def test_history_append_and_read_tail(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    for i in range(5):
        append_history(path, HistoryEntry(session_id=f"s{i}"))
    entries = read_history(path, tail=3)
    assert [e.session_id for e in entries] == ["s2", "s3", "s4"]


def test_history_read_skips_corrupt_line(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    append_history(path, HistoryEntry(session_id="good-1"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not valid json\n")
    append_history(path, HistoryEntry(session_id="good-2"))
    entries = read_history(path)
    ids = [e.session_id for e in entries]
    assert ids == ["good-1", "good-2"]


def test_atomic_write_survives_simulated_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force `os.replace` to raise after the tempfile is written.
    The destination should keep its prior content, and no stray
    tempfile should remain."""
    ensure_bearings_dir(tmp_path)
    path = bearings_path(tmp_path) / "pending.toml"
    write_toml_model(path, Pending(operations=[PendingOperation(name="before")]))

    original_replace = os.replace

    def boom(src: str, dst: str) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr("bearings.bearings_dir.io.os.replace", boom)
    with pytest.raises(OSError):
        write_toml_model(path, Pending(operations=[PendingOperation(name="after")]))

    monkeypatch.setattr("bearings.bearings_dir.io.os.replace", original_replace)
    loaded = read_toml_model(path, Pending)
    assert loaded is not None
    assert [op.name for op in loaded.operations] == ["before"]

    # No lingering tempfiles.
    strays = [p for p in bearings_path(tmp_path).iterdir() if p.name.startswith(".pending.toml.")]
    assert strays == []
