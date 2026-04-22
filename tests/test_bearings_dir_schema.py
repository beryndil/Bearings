"""Unit tests for the `.bearings/` Pydantic schemas.

Locks the field caps described in the spec (description ≤ 500,
summary ≤ 200, etc.) and confirms extra keys are rejected so a
hand-edited typo surfaces instead of silently dropping."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bearings.bearings_dir.schema import (
    EnvironmentBlock,
    HistoryEntry,
    Manifest,
    Pending,
    PendingOperation,
    State,
)


def test_manifest_description_cap() -> None:
    too_long = "x" * 501
    with pytest.raises(ValidationError):
        Manifest(name="x", path="/tmp/x", description=too_long)


def test_manifest_accepts_500_exact() -> None:
    exact = "x" * 500
    m = Manifest(name="x", path="/tmp/x", description=exact)
    assert len(m.description) == 500


def test_manifest_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate({"name": "x", "path": "/tmp/x", "bogus": "yes"})


def test_state_defaults_populate_environment() -> None:
    s = State()
    assert isinstance(s.environment, EnvironmentBlock)
    assert isinstance(s.environment.last_validated, datetime)
    assert s.environment.last_validated.tzinfo is not None


def test_pending_operation_defaults_timezone_aware() -> None:
    op = PendingOperation(name="migrate")
    assert op.started.tzinfo is not None
    assert op.started <= datetime.now(UTC)


def test_pending_caps_operation_count() -> None:
    ops = [PendingOperation(name=f"op{i}") for i in range(65)]
    with pytest.raises(ValidationError):
        Pending(operations=ops)


def test_history_entry_summary_cap() -> None:
    too_long = "x" * 201
    with pytest.raises(ValidationError):
        HistoryEntry(session_id="s", summary=too_long)


def test_history_entry_accepts_200_exact() -> None:
    exact = "x" * 200
    entry = HistoryEntry(session_id="s", summary=exact)
    assert len(entry.summary) == 200


def test_environment_block_notes_cap_entries() -> None:
    with pytest.raises(ValidationError):
        EnvironmentBlock(notes=[f"note-{i}" for i in range(65)])


def test_environment_block_notes_cap_entry_length() -> None:
    with pytest.raises(ValidationError):
        EnvironmentBlock(notes=["y" * 201])
