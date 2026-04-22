"""Pending-operations CRUD — the key `.bearings/` surface.

`pending.toml` is THE file that makes the Directory Context System
worth building: when a session opens and something was left mid-
flight, the record is here, not in chat memory that a new window
never saw.

Semantics:
  - `add(name, ...)` is idempotent on name. Re-adding with the same
    name updates description/command/owner and does NOT reset
    `started`. Rationale: two sessions both "noticing" the same
    broken lockfile shouldn't reset the age clock — the 30-day stale
    flag depends on the original start time.
  - `resolve(name)` removes exactly one matching entry, returns the
    removed `PendingOperation` or `None`. Not an error to resolve
    something that doesn't exist — a retry should be harmless.
  - `list_ops()` returns a snapshot. The caller sees a stable list
    even if another process writes between calls.

Concurrent writers: each operation acquires the file's flock
exclusively for the read-modify-write window. On Unix this is
cross-process safe. On Windows it's advisory only and Bearings is
single-session there — documented tradeoff from the v0.4 spec.
"""

from __future__ import annotations

from pathlib import Path

from bearings.bearings_dir.io import (
    PENDING_FILE,
    bearings_path,
    ensure_bearings_dir,
    read_toml_model,
    write_toml_model,
)
from bearings.bearings_dir.schema import Pending, PendingOperation


def _pending_path(directory: Path) -> Path:
    return bearings_path(directory) / PENDING_FILE


def _load(directory: Path) -> Pending:
    """Read `pending.toml` or return an empty `Pending` on miss.

    A corrupted file is quarantined by `read_toml_model` and we start
    fresh — the quarantine preserves forensics, but pending ops can't
    block CLI usage by being unreadable.
    """
    path = _pending_path(directory)
    loaded = read_toml_model(path, Pending)
    return loaded if loaded is not None else Pending()


def _save(directory: Path, pending: Pending) -> None:
    """Ensure `.bearings/` exists and atomically write `pending.toml`.

    The `.bearings/` directory is created lazily on first write so
    `bearings pending add` doesn't require a prior `bearings here
    init` — useful for capturing an op mid-thought before formal
    onboarding.
    """
    ensure_bearings_dir(directory)
    write_toml_model(_pending_path(directory), pending)


def list_ops(directory: Path) -> list[PendingOperation]:
    """Snapshot of all pending operations, oldest first."""
    ops = list(_load(directory).operations)
    ops.sort(key=lambda op: op.started)
    return ops


def add(
    directory: Path,
    name: str,
    *,
    description: str = "",
    command: str | None = None,
    owner: str | None = None,
) -> PendingOperation:
    """Add or update a pending op. Idempotent on `name`.

    If an op with this name already exists, its `started` is
    preserved (age matters for stale-op detection) and the remaining
    fields are overwritten. A fresh op uses `_utc_now()` via the
    schema default.
    """
    pending = _load(directory)
    existing_idx: int | None = None
    for idx, op in enumerate(pending.operations):
        if op.name == name:
            existing_idx = idx
            break

    if existing_idx is not None:
        # Update-in-place: copy forward `started` so the age clock
        # doesn't reset on a re-notice.
        prior = pending.operations[existing_idx]
        updated = PendingOperation(
            name=name,
            description=description,
            command=command,
            owner=owner if owner is not None else prior.owner,
            started=prior.started,
        )
        pending.operations[existing_idx] = updated
        result = updated
    else:
        new_op = PendingOperation(
            name=name,
            description=description,
            command=command,
            owner=owner,
        )
        pending.operations.append(new_op)
        result = new_op

    _save(directory, pending)
    return result


def resolve(directory: Path, name: str) -> PendingOperation | None:
    """Remove the op with this name. Returns the removed op or `None`
    when no match exists. Not an error to resolve an unknown name —
    retries and replays stay safe.
    """
    pending = _load(directory)
    for idx, op in enumerate(pending.operations):
        if op.name == name:
            removed = pending.operations.pop(idx)
            _save(directory, pending)
            return removed
    return None


def get(directory: Path, name: str) -> PendingOperation | None:
    """Fetch one op by name without mutating the file."""
    for op in _load(directory).operations:
        if op.name == name:
            return op
    return None


__all__ = ["add", "get", "list_ops", "resolve"]
