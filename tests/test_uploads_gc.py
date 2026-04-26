"""Tests for the upload-directory garbage collector.

The sweep is the L5.9 follow-up to the v0.10 DnD upload pipeline:
`/api/uploads` writes one UUID subdir per drop, and without GC the
directory grows monotonically across the lifetime of the install.
These tests verify the pure logic in `bearings.uploads_gc` — the CLI
wrapper exercises the same code path and gets a smoke test
separately via `tests/test_cli.py` if/when one lands.

Layout under test mirrors `routes_uploads`:

    <upload_root>/
      <uuid32-old>/file.txt   <- expired
      <uuid32-new>/file.txt   <- recent
      not-a-uuid/file.txt     <- never touched (defensive)
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from bearings.uploads_gc import (
    ExpiredSubdir,
    SweepResult,
    find_expired_subdirs,
    prune_subdirs,
)


def _make_subdir(root: Path, name: str | None = None, *, contents: bytes = b"x") -> Path:
    """Build a single UUID-named subdir with one file inside it.

    Returns the subdir path. `name` defaults to a fresh UUID4 hex —
    the format the upload route uses. Pass an explicit string when a
    test wants to assert the defensive non-UUID skip.
    """
    sub = root / (name or uuid.uuid4().hex)
    sub.mkdir(parents=True)
    (sub / "file.txt").write_bytes(contents)
    return sub


def _set_mtime(path: Path, when_epoch: float) -> None:
    """Touch every file (and the dir itself) under `path` to a fixed
    mtime. Sweep keys on the *newest* mtime under the dir, so we have
    to push every entry back, not just the directory inode."""
    os.utime(path, (when_epoch, when_epoch))
    for entry in path.rglob("*"):
        os.utime(entry, (when_epoch, when_epoch))


def test_find_expired_returns_empty_when_root_missing(tmp_path: Path) -> None:
    """A fresh install has no upload dir yet — the route auto-creates
    on first POST. The sweep treats a missing dir as a valid empty
    state, not an error."""
    missing = tmp_path / "uploads"
    assert find_expired_subdirs(missing, cutoff_epoch=time.time()) == []


def test_find_expired_picks_up_old_subdirs(tmp_path: Path) -> None:
    """Subdirs whose newest mtime is older than the cutoff get
    flagged. A fresh subdir under the same root does not. Both must
    be UUID-named so the defensive shape filter doesn't drop them."""
    root = tmp_path / "uploads"
    root.mkdir()
    now = time.time()
    old = _make_subdir(root, contents=b"old payload")
    fresh = _make_subdir(root, contents=b"new")
    _set_mtime(old, now - 60 * 86400)  # 60 days back
    _set_mtime(fresh, now - 1 * 86400)  # 1 day back

    cutoff = now - 30 * 86400  # 30-day retention
    expired = find_expired_subdirs(root, cutoff_epoch=cutoff)

    paths = {e.path for e in expired}
    assert paths == {old}
    assert fresh.exists()  # find is read-only, it never mutates


def test_find_expired_ignores_non_uuid_subdirs(tmp_path: Path) -> None:
    """A hand-created subdir with a non-UUID name (user dropped a
    backup directory in there) must be untouched even when its mtime
    is ancient. Defensive shape-check exists exactly so a config
    typo or stray cp -r can't make the sweep delete user data."""
    root = tmp_path / "uploads"
    root.mkdir()
    now = time.time()
    rogue = _make_subdir(root, name="my-personal-stash")
    _set_mtime(rogue, now - 365 * 86400)  # one year old

    expired = find_expired_subdirs(root, cutoff_epoch=now)
    assert expired == []


def test_find_expired_ignores_top_level_files(tmp_path: Path) -> None:
    """A file dropped directly into the upload root (not the route's
    fault — it'd never put one there — but possible via hand-edit)
    must not crash the sweep or get its mtime sampled."""
    root = tmp_path / "uploads"
    root.mkdir()
    (root / "loose-file.txt").write_bytes(b"hi")
    now = time.time()
    os.utime(root / "loose-file.txt", (now - 999 * 86400, now - 999 * 86400))

    expired = find_expired_subdirs(root, cutoff_epoch=now)
    assert expired == []


def test_find_expired_uses_newest_mtime_under_dir(tmp_path: Path) -> None:
    """Sweep keys on the newest mtime in the tree, not the dir's own
    mtime. A subdir whose dir-inode is old but whose file inside was
    just touched (re-read by the agent) must NOT be pruned."""
    root = tmp_path / "uploads"
    root.mkdir()
    now = time.time()
    sub = _make_subdir(root)
    # Push the dir inode back, but leave the file recent.
    os.utime(sub, (now - 999 * 86400, now - 999 * 86400))
    os.utime(sub / "file.txt", (now - 1 * 86400, now - 1 * 86400))

    expired = find_expired_subdirs(root, cutoff_epoch=now - 30 * 86400)
    assert expired == []


def test_find_expired_results_sorted_oldest_first(tmp_path: Path) -> None:
    """Dry-run output reads as a chronological list; sort order is
    part of the contract. Operator scans top-down and stops where
    comfort runs out."""
    root = tmp_path / "uploads"
    root.mkdir()
    now = time.time()
    a = _make_subdir(root)
    b = _make_subdir(root)
    c = _make_subdir(root)
    _set_mtime(a, now - 100 * 86400)
    _set_mtime(b, now - 200 * 86400)
    _set_mtime(c, now - 50 * 86400)

    expired = find_expired_subdirs(root, cutoff_epoch=now - 30 * 86400)
    assert [e.path for e in expired] == [b, a, c]


def test_find_expired_records_size_bytes(tmp_path: Path) -> None:
    """Summary line wants `freed M bytes`; sweep must capture size up
    front so the prune doesn't have to re-walk a tree it's about to
    delete."""
    root = tmp_path / "uploads"
    root.mkdir()
    now = time.time()
    sub = _make_subdir(root, contents=b"X" * 4096)
    _set_mtime(sub, now - 60 * 86400)

    expired = find_expired_subdirs(root, cutoff_epoch=now - 30 * 86400)
    assert len(expired) == 1
    assert expired[0].size_bytes == 4096


def test_prune_subdirs_removes_and_tallies(tmp_path: Path) -> None:
    """Happy path: every flagged dir is removed, counts add up, no
    errors. The result's `freed_bytes` matches the input's total."""
    root = tmp_path / "uploads"
    root.mkdir()
    now = time.time()
    a = _make_subdir(root, contents=b"a" * 100)
    b = _make_subdir(root, contents=b"b" * 200)
    _set_mtime(a, now - 60 * 86400)
    _set_mtime(b, now - 60 * 86400)

    expired = find_expired_subdirs(root, cutoff_epoch=now - 30 * 86400)
    result = prune_subdirs(expired)

    assert isinstance(result, SweepResult)
    assert result.removed == 2
    assert result.freed_bytes == 300
    assert result.errors == []
    assert not a.exists()
    assert not b.exists()


def test_prune_subdirs_records_errors_without_aborting(tmp_path: Path, monkeypatch) -> None:
    """One failure must not strand the rest. Simulate an OSError on
    the first target via monkeypatched `shutil.rmtree`; the second
    still goes through."""
    import bearings.uploads_gc as gc

    root = tmp_path / "uploads"
    root.mkdir()
    now = time.time()
    a = _make_subdir(root)
    b = _make_subdir(root)

    targets = [
        ExpiredSubdir(path=a, newest_mtime=now - 60 * 86400, size_bytes=1),
        ExpiredSubdir(path=b, newest_mtime=now - 60 * 86400, size_bytes=2),
    ]

    real_rmtree = gc.shutil.rmtree
    calls: list[Path] = []

    def flaky_rmtree(target: Path, *args: object, **kwargs: object) -> None:
        calls.append(target)
        if target == a:
            raise OSError("simulated permission failure")
        real_rmtree(target, *args, **kwargs)

    monkeypatch.setattr(gc.shutil, "rmtree", flaky_rmtree)

    result = prune_subdirs(targets)

    assert calls == [a, b]  # second target attempted despite first failure
    assert result.removed == 1
    assert result.freed_bytes == 2  # only b's size counted
    assert len(result.errors) == 1
    assert result.errors[0][0] == a
    assert "simulated" in result.errors[0][1]


def test_zero_retention_treats_everything_as_expired(tmp_path: Path) -> None:
    """`bearings gc uploads --retention-days 0` should sweep the lot.
    Cutoff = now means every existing dir's newest mtime is strictly
    less than the cutoff (microsecond gap), so all UUID dirs flag."""
    root = tmp_path / "uploads"
    root.mkdir()
    _make_subdir(root)
    _make_subdir(root)
    # Pin both back a microsecond so the strict inequality lands.
    cutoff = time.time() + 1
    expired = find_expired_subdirs(root, cutoff_epoch=cutoff)
    assert len(expired) == 2
