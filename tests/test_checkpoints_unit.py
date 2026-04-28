"""Unit tests for :class:`bearings.db.checkpoints.Checkpoint`.

Validates dataclass shape and ``__post_init__`` constraints without
opening a DB connection — the integration tests in
``test_checkpoints_integration.py`` exercise the round-trip.

References:

* ``docs/architecture-v1.md`` §1.1.3 + §5 #12 — checkpoints table is
  Bearings' own named-snapshot surface, not the SDK
  ``enable_file_checkpointing`` primitive.
* ``docs/behavior/chat.md`` §"Slash commands in the composer" — the
  ``/checkpoint`` command inserts a labelled gutter mark.
* ``docs/behavior/context-menus.md`` §"Checkpoint (gutter chip)" —
  primary action ``checkpoint.fork``; no "restore" action exists.
"""

from __future__ import annotations

import pytest

from bearings.config.constants import CHECKPOINT_LABEL_MAX_LENGTH
from bearings.db.checkpoints import Checkpoint


def _valid_kwargs() -> dict[str, str]:
    return {
        "id": "cpt_0123456789abcdef0123456789abcdef",
        "session_id": "session_abc",
        "message_id": "msg_xyz",
        "label": "Before refactor",
        "created_at": "2026-04-28T12:00:00+00:00",
    }


def test_checkpoint_constructs_with_valid_fields() -> None:
    """Happy path: every field non-empty, label within cap."""
    cp = Checkpoint(**_valid_kwargs())
    assert cp.id == "cpt_0123456789abcdef0123456789abcdef"
    assert cp.label == "Before refactor"


def test_checkpoint_is_frozen() -> None:
    """Frozen dataclass: attribute assignment must raise."""
    cp = Checkpoint(**_valid_kwargs())
    with pytest.raises((AttributeError, TypeError)):
        cp.label = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize("field_name", ["id", "session_id", "message_id", "label", "created_at"])
def test_checkpoint_rejects_empty_required_field(field_name: str) -> None:
    """Every required field must be non-empty."""
    kwargs = _valid_kwargs()
    kwargs[field_name] = ""
    with pytest.raises(ValueError, match=field_name):
        Checkpoint(**kwargs)


def test_checkpoint_rejects_label_above_cap() -> None:
    """A label > CHECKPOINT_LABEL_MAX_LENGTH chars raises ValueError."""
    kwargs = _valid_kwargs()
    kwargs["label"] = "x" * (CHECKPOINT_LABEL_MAX_LENGTH + 1)
    with pytest.raises(ValueError, match="≤"):
        Checkpoint(**kwargs)


def test_checkpoint_accepts_label_at_cap() -> None:
    """A label at exactly the cap is valid (boundary inclusive)."""
    kwargs = _valid_kwargs()
    kwargs["label"] = "x" * CHECKPOINT_LABEL_MAX_LENGTH
    cp = Checkpoint(**kwargs)
    assert len(cp.label) == CHECKPOINT_LABEL_MAX_LENGTH
