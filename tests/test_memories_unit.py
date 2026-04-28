"""Unit tests for :class:`bearings.db.memories.TagMemory`.

References:

* ``docs/architecture-v1.md`` §1.1.3 — tag_memories table.
* arch §6.3 — "Layered system-prompt assembler with per-turn re-read"
  for the lifecycle (enabled flag).
"""

from __future__ import annotations

import pytest

from bearings.config.constants import (
    TAG_MEMORY_BODY_MAX_LENGTH,
    TAG_MEMORY_TITLE_MAX_LENGTH,
)
from bearings.db.memories import TagMemory


def _valid_kwargs() -> dict[str, object]:
    return {
        "id": 1,
        "tag_id": 7,
        "title": "Architectural anchors",
        "body": "Always cite arch §1.1.3 when introducing a concern module.",
        "enabled": True,
        "created_at": "2026-04-28T12:00:00+00:00",
        "updated_at": "2026-04-28T12:00:00+00:00",
    }


def test_memory_constructs_with_valid_fields() -> None:
    m = TagMemory(**_valid_kwargs())  # type: ignore[arg-type]
    assert m.title == "Architectural anchors"
    assert m.enabled is True


def test_memory_is_frozen() -> None:
    m = TagMemory(**_valid_kwargs())  # type: ignore[arg-type]
    with pytest.raises((AttributeError, TypeError)):
        m.title = "renamed"  # type: ignore[misc]


def test_memory_rejects_empty_title() -> None:
    kwargs = _valid_kwargs()
    kwargs["title"] = ""
    with pytest.raises(ValueError, match="title"):
        TagMemory(**kwargs)  # type: ignore[arg-type]


def test_memory_rejects_title_above_cap() -> None:
    kwargs = _valid_kwargs()
    kwargs["title"] = "x" * (TAG_MEMORY_TITLE_MAX_LENGTH + 1)
    with pytest.raises(ValueError, match="≤"):
        TagMemory(**kwargs)  # type: ignore[arg-type]


def test_memory_rejects_empty_body() -> None:
    kwargs = _valid_kwargs()
    kwargs["body"] = ""
    with pytest.raises(ValueError, match="body"):
        TagMemory(**kwargs)  # type: ignore[arg-type]


def test_memory_rejects_body_above_cap() -> None:
    kwargs = _valid_kwargs()
    kwargs["body"] = "y" * (TAG_MEMORY_BODY_MAX_LENGTH + 1)
    with pytest.raises(ValueError, match="≤"):
        TagMemory(**kwargs)  # type: ignore[arg-type]


def test_memory_rejects_non_positive_tag_id() -> None:
    kwargs = _valid_kwargs()
    kwargs["tag_id"] = 0
    with pytest.raises(ValueError, match="tag_id"):
        TagMemory(**kwargs)  # type: ignore[arg-type]
