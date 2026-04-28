"""Unit tests for :class:`bearings.db.templates.Template`.

Validates dataclass shape, ``__post_init__`` constraints, and the
JSON-array ``tag_names`` round-trip helpers without opening a DB.

References:

* ``docs/architecture-v1.md`` §1.1.3 — templates table.
* ``docs/model-routing-v1-spec.md`` §App A — executor / advisor /
  effort field alphabets, mirrored in the dataclass validator.
* ``docs/behavior/chat.md`` — new-session-from-template flow.
"""

from __future__ import annotations

import pytest

from bearings.config.constants import (
    TEMPLATE_DESCRIPTION_MAX_LENGTH,
    TEMPLATE_NAME_MAX_LENGTH,
)
from bearings.db.templates import (
    Template,
    _tag_names_from_json,
    _tag_names_to_json,
)


def _valid_kwargs() -> dict[str, object]:
    return {
        "id": 1,
        "name": "Workhorse",
        "description": "Sonnet + Opus advisor; standard permissions.",
        "model": "sonnet",
        "advisor_model": "opus",
        "advisor_max_uses": 5,
        "effort_level": "auto",
        "permission_profile": "standard",
        "system_prompt_baseline": None,
        "working_dir_default": "/home/user/work",
        "tag_names": ("bearings/architect", "bearings/exec"),
        "created_at": "2026-04-28T12:00:00+00:00",
        "updated_at": "2026-04-28T12:00:00+00:00",
    }


def test_template_constructs_with_valid_fields() -> None:
    """Happy path: every field within its alphabet."""
    template = Template(**_valid_kwargs())  # type: ignore[arg-type]
    assert template.name == "Workhorse"
    assert template.tag_names == ("bearings/architect", "bearings/exec")


def test_template_is_frozen() -> None:
    """Frozen dataclass: attribute assignment raises."""
    template = Template(**_valid_kwargs())  # type: ignore[arg-type]
    with pytest.raises((AttributeError, TypeError)):
        template.name = "renamed"  # type: ignore[misc]


def test_template_rejects_empty_name() -> None:
    kwargs = _valid_kwargs()
    kwargs["name"] = ""
    with pytest.raises(ValueError, match="name"):
        Template(**kwargs)  # type: ignore[arg-type]


def test_template_rejects_name_above_cap() -> None:
    kwargs = _valid_kwargs()
    kwargs["name"] = "x" * (TEMPLATE_NAME_MAX_LENGTH + 1)
    with pytest.raises(ValueError, match="≤"):
        Template(**kwargs)  # type: ignore[arg-type]


def test_template_rejects_description_above_cap() -> None:
    kwargs = _valid_kwargs()
    kwargs["description"] = "y" * (TEMPLATE_DESCRIPTION_MAX_LENGTH + 1)
    with pytest.raises(ValueError, match="≤"):
        Template(**kwargs)  # type: ignore[arg-type]


def test_template_rejects_unknown_executor() -> None:
    kwargs = _valid_kwargs()
    kwargs["model"] = "sonet"  # codespell:ignore sonet — typo deliberate for the test
    with pytest.raises(ValueError, match="model"):
        Template(**kwargs)  # type: ignore[arg-type]


def test_template_rejects_unknown_advisor_unless_full_id() -> None:
    """Advisor short name must be known; full ``claude-`` IDs accepted."""
    kwargs = _valid_kwargs()
    kwargs["advisor_model"] = "oppus"  # typo
    with pytest.raises(ValueError, match="advisor_model"):
        Template(**kwargs)  # type: ignore[arg-type]
    # Full SDK ID with the canonical prefix passes.
    kwargs2 = _valid_kwargs()
    kwargs2["advisor_model"] = "claude-opus-4-1"
    Template(**kwargs2)  # type: ignore[arg-type]


def test_template_rejects_negative_advisor_max_uses() -> None:
    kwargs = _valid_kwargs()
    kwargs["advisor_max_uses"] = -1
    with pytest.raises(ValueError, match="≥ 0"):
        Template(**kwargs)  # type: ignore[arg-type]


def test_template_rejects_unknown_effort_level() -> None:
    kwargs = _valid_kwargs()
    kwargs["effort_level"] = "ultra"
    with pytest.raises(ValueError, match="effort_level"):
        Template(**kwargs)  # type: ignore[arg-type]


def test_template_rejects_unknown_permission_profile() -> None:
    kwargs = _valid_kwargs()
    kwargs["permission_profile"] = "ninja"
    with pytest.raises(ValueError, match="permission_profile"):
        Template(**kwargs)  # type: ignore[arg-type]


def test_template_accepts_no_advisor() -> None:
    """A template can declare an Opus-solo executor with no advisor."""
    kwargs = _valid_kwargs()
    kwargs["model"] = "opus"
    kwargs["advisor_model"] = None
    kwargs["advisor_max_uses"] = 0
    kwargs["effort_level"] = "xhigh"
    template = Template(**kwargs)  # type: ignore[arg-type]
    assert template.advisor_model is None


def test_tag_names_round_trip_preserves_order() -> None:
    """JSON serialisation preserves both content and order."""
    names = ("alpha", "beta", "gamma")
    payload = _tag_names_to_json(names)
    assert _tag_names_from_json(payload) == names


def test_tag_names_round_trip_empty() -> None:
    """Empty tag set serialises to ``[]`` and round-trips."""
    assert _tag_names_to_json(()) == "[]"
    assert _tag_names_from_json("[]") == ()


def test_tag_names_from_json_rejects_malformed_json() -> None:
    with pytest.raises(ValueError, match="JSON"):
        _tag_names_from_json("{not json}")


def test_tag_names_from_json_rejects_non_array() -> None:
    with pytest.raises(ValueError, match="array"):
        _tag_names_from_json('"a string, not an array"')


def test_tag_names_from_json_rejects_non_string_entries() -> None:
    with pytest.raises(ValueError, match="string"):
        _tag_names_from_json("[1, 2, 3]")
