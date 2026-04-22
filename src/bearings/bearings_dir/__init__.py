"""Directory Context System — per-directory ground truth on disk.

Each tracked directory gets a `.bearings/` folder whose contents any
session can read to learn what's happening here instead of relying on
ephemeral chat memory. The premise: an agent's claims about the world
should never be trusted over what's actually written down.

Layout::

    .bearings/
    ├── manifest.toml     # identity — slow-changing
    ├── state.toml        # per-session belief about current state
    ├── pending.toml      # operations in flight (THE key file)
    ├── history.jsonl     # append-only session log
    └── checks/on_open.sh # optional user-written health probe

v0.6.0 ships the foundation: schemas, atomic IO, onboarding ritual,
pending CRUD, and `bearings here init` / `bearings here check` /
`bearings pending …` CLI surfaces. Agent-prompt integration,
auto-onboarding, and the on_open.sh runner follow in v0.6.1+.
"""

from __future__ import annotations

from bearings.bearings_dir.schema import (
    EnvironmentBlock,
    HistoryEntry,
    Manifest,
    Pending,
    PendingOperation,
    State,
)

__all__ = [
    "EnvironmentBlock",
    "HistoryEntry",
    "Manifest",
    "Pending",
    "PendingOperation",
    "State",
]
