"""Time-based garbage collection for the upload directory.

`/api/uploads` writes each browser-dropped file under
`<upload_dir>/<uuid>/<sanitized-name>`. Once the agent has read the
file the bytes are dead weight on disk — Claude doesn't re-read the
path on a later turn, the user doesn't open it, nothing references
the UUID dir again. Without a sweep the directory grows monotonically
across the lifetime of the install.

This module provides the pure logic; the `bearings gc uploads` CLI
subcommand drives it. Two-phase by design:

  1. `find_expired_subdirs` — walks the upload root, returns the
     UUID subdirs whose newest mtime is older than the cutoff. Pure,
     no side effects, easy to test and easy to dry-run.
  2. `prune_subdirs` — unlinks the directories returned by step 1.
     Returns a `SweepResult` with counts + freed bytes for the
     CLI's summary line.

We bucket per-UUID-dir rather than per-file because that's the unit
the upload route creates: one drop = one UUID dir = one file inside
it. Walking by directory keeps the sweep O(N drops), not O(N files
in the entire tree). It also means a hand-edit (user copies a file
out of a UUID dir for safekeeping) leaves a stable directory the
sweep won't touch as long as something inside it has a recent mtime.

Safety boundary: the sweep ONLY operates on direct children of
`upload_dir` whose names are valid 32-hex UUID strings. Files dropped
straight into the root, hand-created subdirectories with non-UUID
names, and anything outside the configured root are all ignored. A
config typo can't make this delete `~`.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

# UUID4 hex without dashes — the exact shape `uuid.uuid4().hex`
# produces in `routes_uploads.upload_file`. Anchored both ends so a
# stray prefix/suffix doesn't sneak in.
_UUID_HEX_RE = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class ExpiredSubdir:
    """One UUID subdirectory the sweep has decided is expired.

    `path` is absolute. `newest_mtime` is the most recent mtime under
    the dir (in epoch seconds) — used by callers that want to render
    `expired N days ago` next to each path. `size_bytes` is the
    cumulative on-disk size of every file under the dir, so the
    summary line can report "freed M bytes" without re-walking.
    """

    path: Path
    newest_mtime: float
    size_bytes: int


@dataclass
class SweepResult:
    """Outcome of `prune_subdirs`. `removed` is the count of UUID dirs
    actually unlinked; `freed_bytes` is the cumulative size of those
    dirs at the moment they were measured. `errors` carries one entry
    per dir the sweep tried to remove but couldn't (permissions, race
    with a concurrent uploader). The CLI prints these to stderr so the
    operator notices a recurring failure instead of having it eaten
    silently."""

    removed: int = 0
    freed_bytes: int = 0
    errors: list[tuple[Path, str]] = field(default_factory=list)


def _newest_mtime_under(dir_path: Path) -> float:
    """Return the most recent mtime of any file inside `dir_path`,
    falling back to the directory's own mtime when it's empty.

    Uses the *newest* timestamp rather than the directory's own mtime
    so a dir whose contents were just touched (e.g. agent re-read the
    file, OS updated atime+mtime via tail-write) doesn't get pruned
    out from under an active session. Empty UUID dirs collapse to
    their own mtime, which means a half-completed reject (the route
    cleans these up itself, but defense in depth is cheap) still
    expires on the same schedule as a successful drop."""
    newest = dir_path.stat().st_mtime
    for entry in dir_path.rglob("*"):
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            # Broken symlink or race with concurrent removal — skip
            # this entry, the directory's own mtime stays the floor.
            continue
        if mtime > newest:
            newest = mtime
    return newest


def _size_under(dir_path: Path) -> int:
    """Sum of `st_size` for every file under `dir_path`, in bytes.

    Symlinks are followed only one level (we resolve `is_file()` on
    the original path; `stat()` follows the link to size the target).
    A symlink loop would be a pathological hand-edit; the upload route
    never creates them. OSError on any entry (broken link, race) is
    swallowed — the byte count is informational, not authoritative."""
    total = 0
    for entry in dir_path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def find_expired_subdirs(
    upload_dir: Path,
    *,
    cutoff_epoch: float,
) -> list[ExpiredSubdir]:
    """Return the UUID subdirs of `upload_dir` whose newest mtime is
    strictly older than `cutoff_epoch`.

    `cutoff_epoch` is seconds since the epoch — typically
    `time.time() - retention_days * 86400`, computed by the caller so
    tests can pin "now" without mocking the clock here. Strictly older
    (not `<=`) so a sweep run exactly at the boundary doesn't race a
    write that landed a microsecond before.

    A missing or empty `upload_dir` returns `[]` — the route auto-
    creates the dir on first upload, so a fresh install with no drops
    yet is a valid state, not an error.
    """
    if not upload_dir.exists() or not upload_dir.is_dir():
        return []
    expired: list[ExpiredSubdir] = []
    for child in upload_dir.iterdir():
        # Defensive: only sweep directories the upload route itself
        # could have created. A user-managed file in the root or a
        # rogue subdirectory with a non-UUID name is left alone.
        if not child.is_dir():
            continue
        if not _UUID_HEX_RE.match(child.name):
            continue
        newest = _newest_mtime_under(child)
        if newest >= cutoff_epoch:
            continue
        expired.append(
            ExpiredSubdir(
                path=child,
                newest_mtime=newest,
                size_bytes=_size_under(child),
            )
        )
    # Sort oldest-first so the CLI's dry-run output reads as a
    # chronological list — operator scans from "ancient" down to
    # "just barely over the line" and stops where comfort runs out.
    expired.sort(key=lambda e: e.newest_mtime)
    return expired


def prune_subdirs(targets: Iterable[ExpiredSubdir]) -> SweepResult:
    """Recursively remove each `ExpiredSubdir` and tally the result.

    `shutil.rmtree` per dir — the upload route writes one file into a
    UUID parent, so the trees are tiny and the recursive walk is
    cheap. `ignore_errors=False` so a permission problem surfaces
    rather than silently leaving a half-pruned tree on disk.

    Errors don't abort the sweep — a permission failure on one dir
    shouldn't strand twenty newer expired drops downstream. Each
    failure lands in `result.errors` for the CLI to report.
    """
    result = SweepResult()
    for target in targets:
        try:
            shutil.rmtree(target.path)
        except OSError as exc:
            result.errors.append((target.path, str(exc)))
            continue
        result.removed += 1
        result.freed_bytes += target.size_bytes
    return result
