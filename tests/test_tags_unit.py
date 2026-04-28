"""Unit tests for :class:`bearings.db.tags.Tag`.

Validates dataclass shape, ``__post_init__`` constraints, and the
``group`` property's slash-namespace parsing without opening a DB.

References:

* ``docs/architecture-v1.md`` §1.1.3 — tags table.
* ``docs/model-routing-v1-spec.md`` §App A — executor model alphabet
  the dataclass mirrors for ``default_model``.
* ``docs/behavior/checklists.md`` — inheritance fields
  (``default_model``, ``working_dir``).
"""

from __future__ import annotations

import pytest

from bearings.config.constants import TAG_COLOR_MAX_LENGTH, TAG_NAME_MAX_LENGTH
from bearings.db.tags import Tag


def _valid_kwargs() -> dict[str, object]:
    return {
        "id": 1,
        "name": "bearings/architect",
        "color": "#ffaa00",
        "default_model": "opus",
        "working_dir": "/home/dave/project",
        "created_at": "2026-04-28T12:00:00+00:00",
        "updated_at": "2026-04-28T12:00:00+00:00",
    }


def test_tag_constructs_with_valid_fields() -> None:
    tag = Tag(**_valid_kwargs())  # type: ignore[arg-type]
    assert tag.name == "bearings/architect"
    assert tag.default_model == "opus"


def test_tag_is_frozen() -> None:
    tag = Tag(**_valid_kwargs())  # type: ignore[arg-type]
    with pytest.raises((AttributeError, TypeError)):
        tag.name = "renamed"  # type: ignore[misc]


def test_tag_rejects_empty_name() -> None:
    kwargs = _valid_kwargs()
    kwargs["name"] = ""
    with pytest.raises(ValueError, match="name"):
        Tag(**kwargs)  # type: ignore[arg-type]


def test_tag_rejects_name_above_cap() -> None:
    kwargs = _valid_kwargs()
    kwargs["name"] = "x" * (TAG_NAME_MAX_LENGTH + 1)
    with pytest.raises(ValueError, match="≤"):
        Tag(**kwargs)  # type: ignore[arg-type]


def test_tag_rejects_color_above_cap() -> None:
    kwargs = _valid_kwargs()
    kwargs["color"] = "y" * (TAG_COLOR_MAX_LENGTH + 1)
    with pytest.raises(ValueError, match="color"):
        Tag(**kwargs)  # type: ignore[arg-type]


def test_tag_rejects_unknown_default_model() -> None:
    kwargs = _valid_kwargs()
    kwargs["default_model"] = "sonet"  # codespell:ignore sonet — typo deliberate for the test
    with pytest.raises(ValueError, match="default_model"):
        Tag(**kwargs)  # type: ignore[arg-type]


def test_tag_accepts_full_sdk_id_default_model() -> None:
    kwargs = _valid_kwargs()
    kwargs["default_model"] = "claude-sonnet-4-5"
    tag = Tag(**kwargs)  # type: ignore[arg-type]
    assert tag.default_model == "claude-sonnet-4-5"


def test_tag_accepts_no_default_model() -> None:
    kwargs = _valid_kwargs()
    kwargs["default_model"] = None
    tag = Tag(**kwargs)  # type: ignore[arg-type]
    assert tag.default_model is None


def test_tag_rejects_empty_working_dir() -> None:
    kwargs = _valid_kwargs()
    kwargs["working_dir"] = ""
    with pytest.raises(ValueError, match="working_dir"):
        Tag(**kwargs)  # type: ignore[arg-type]


def test_tag_accepts_no_working_dir() -> None:
    kwargs = _valid_kwargs()
    kwargs["working_dir"] = None
    tag = Tag(**kwargs)  # type: ignore[arg-type]
    assert tag.working_dir is None


def test_tag_group_property_extracts_slash_prefix() -> None:
    """``bearings/architect`` → ``bearings``."""
    tag = Tag(**_valid_kwargs())  # type: ignore[arg-type]
    assert tag.group == "bearings"


def test_tag_group_property_returns_none_for_bare_name() -> None:
    """Tag without a separator → default group (``None``)."""
    kwargs = _valid_kwargs()
    kwargs["name"] = "general"
    tag = Tag(**kwargs)  # type: ignore[arg-type]
    assert tag.group is None


def test_tag_group_property_returns_none_for_leading_separator() -> None:
    """Leading slash → default group (``/foo`` is not in the ``foo`` group)."""
    kwargs = _valid_kwargs()
    kwargs["name"] = "/orphan"
    tag = Tag(**kwargs)  # type: ignore[arg-type]
    assert tag.group is None
