"""Tests for :mod:`bearings.config.constants`.

Two responsibilities:

1. Spot-check that spec-mandated values match the spec verbatim. The
   item-0.5 auditor will independently grep the spec for numeric
   literals and confirm coverage; these tests pin the values that
   appear most often in downstream items so a stale value cannot land
   silently.
2. Verify every public name in ``__all__`` is annotated as
   ``Final[...]`` per the coding-standards directive that constants
   carry the marker. With ``from __future__ import annotations`` in
   the constants module, ``__annotations__`` holds the source string
   ``"Final[...]"`` which the assertion can substring-match against.
"""

from __future__ import annotations

from datetime import timedelta

from bearings.config import constants


def test_routing_preview_debounce_matches_spec() -> None:
    """Spec §6 'Reactive behavior' — debounced ~300 ms."""
    assert timedelta(milliseconds=300) == constants.ROUTING_PREVIEW_DEBOUNCE
    assert constants.ROUTING_PREVIEW_DEBOUNCE_MS == 300


def test_usage_poll_interval_matches_spec() -> None:
    """Spec §4 — 'polls /usage every 5 minutes'."""
    assert timedelta(minutes=5) == constants.USAGE_POLL_INTERVAL
    assert constants.USAGE_POLL_INTERVAL_S == 300


def test_quota_thresholds_match_spec() -> None:
    """Spec §4 downgrade trigger; §10 quota-bar colour transitions."""
    assert constants.QUOTA_THRESHOLD_PCT == 0.80
    assert constants.QUOTA_BAR_YELLOW_PCT == 0.80
    assert constants.QUOTA_BAR_RED_PCT == 0.95


def test_override_rate_window_matches_spec() -> None:
    """Spec §8 — override_rate > 0.30 over 14 days surfaced for review."""
    assert constants.OVERRIDE_RATE_REVIEW_THRESHOLD == 0.30
    assert timedelta(days=14) == constants.OVERRIDE_RATE_WINDOW
    assert constants.OVERRIDE_RATE_WINDOW_DAYS == 14


def test_usage_headroom_window_matches_spec() -> None:
    """Spec §7, §10 — 7-day rolling headroom chart."""
    assert timedelta(days=7) == constants.USAGE_HEADROOM_WINDOW
    assert constants.USAGE_HEADROOM_WINDOW_DAYS == 7


def test_advisor_defaults_match_spec() -> None:
    """Spec §2 default-policy table."""
    assert constants.DEFAULT_ADVISOR_MAX_USES_SONNET == 5
    assert constants.DEFAULT_ADVISOR_MAX_USES_HAIKU == 3
    assert constants.ADVISOR_TOOL_BETA_HEADER == "advisor-tool-2026-03-01"


def test_effort_level_to_sdk_table() -> None:
    """Arch §5 #4 — auto omits, xhigh maps to 'max'."""
    assert constants.EFFORT_LEVEL_TO_SDK["auto"] is None
    assert constants.EFFORT_LEVEL_TO_SDK["low"] == "low"
    assert constants.EFFORT_LEVEL_TO_SDK["medium"] == "medium"
    assert constants.EFFORT_LEVEL_TO_SDK["high"] == "high"
    assert constants.EFFORT_LEVEL_TO_SDK["xhigh"] == "max"


def test_executor_fallback_model_table() -> None:
    """Arch §5 #5 — sonnet→haiku, opus→sonnet, haiku→haiku."""
    assert constants.EXECUTOR_FALLBACK_MODEL == {
        "sonnet": "haiku",
        "opus": "sonnet",
        "haiku": "haiku",
    }


def test_v1_repo_invariants_match_claude_md() -> None:
    """CLAUDE.md repo invariants — port 8788, db at bearings-v1 dir."""
    assert constants.DEFAULT_PORT == 8788
    assert constants.DEFAULT_HOST == "127.0.0.1"
    assert "bearings-v1" in str(constants.DEFAULT_DB_PATH)
    assert constants.DEFAULT_DB_PATH.name == "sessions.db"
    assert constants.DEFAULT_DB_PATH.is_absolute()


def test_internal_runtime_defaults() -> None:
    """Arch §1.1.2 example values."""
    assert constants.RING_BUFFER_MAX == 5000
    assert constants.HISTORY_PRIME_MAX_CHARS == 60_000
    assert constants.PRESSURE_INJECT_THRESHOLD_PCT == 70.0
    assert constants.DEFAULT_TOOL_OUTPUT_CAP_CHARS == 8000
    assert constants.TOOL_PROGRESS_INTERVAL_S == 2.0
    assert constants.WS_IDLE_PING_INTERVAL_S == 15.0


def test_checklist_driver_defaults() -> None:
    """behavior/checklists.md — sentinel safety caps."""
    assert constants.CHECKLIST_DRIVER_PRESSURE_HANDOFF_THRESHOLD_PCT == 60.0
    assert constants.CHECKLIST_DRIVER_MAX_LEGS_PER_ITEM == 5
    assert constants.CHECKLIST_DRIVER_MAX_ITEMS_PER_RUN == 50
    assert constants.CHECKLIST_DRIVER_MAX_FOLLOWUP_DEPTH == 3


def test_bearings_todo_recent_default_days() -> None:
    """behavior/bearings-cli.md §'bearings todo recent' — last 7 days."""
    assert constants.BEARINGS_TODO_RECENT_DEFAULT_DAYS == 7


def test_known_executor_models_contains_short_names() -> None:
    """Spec §App A — short-name vocabulary the routing layer accepts."""
    assert "sonnet" in constants.KNOWN_EXECUTOR_MODELS
    assert "haiku" in constants.KNOWN_EXECUTOR_MODELS
    assert "opus" in constants.KNOWN_EXECUTOR_MODELS
    assert "opusplan" in constants.KNOWN_EXECUTOR_MODELS
    assert constants.EXECUTOR_MODEL_FULL_ID_PREFIX == "claude-"


def test_known_effort_levels_match_spec() -> None:
    """Spec §App A — auto / low / medium / high / xhigh."""
    assert frozenset({"auto", "low", "medium", "high", "xhigh"}) == constants.KNOWN_EFFORT_LEVELS


def test_known_routing_sources_match_spec() -> None:
    """Spec §App A — seven RoutingDecision.source enum values."""
    expected = {
        "tag_rule",
        "system_rule",
        "default",
        "manual",
        "quota_downgrade",
        "manual_override_quota",
        "unknown_legacy",
    }
    assert frozenset(expected) == constants.KNOWN_ROUTING_SOURCES


def test_known_sdk_permission_modes_match_sdk() -> None:
    """SDK ``permission_mode`` literal alphabet (context7 query, arch §5)."""
    assert (
        frozenset({"default", "acceptEdits", "plan", "bypassPermissions", "dontAsk", "auto"})
        == constants.KNOWN_SDK_PERMISSION_MODES
    )


def test_known_sdk_setting_sources_match_sdk() -> None:
    """SDK ``setting_sources`` literal alphabet (context7 query)."""
    assert frozenset({"user", "project", "local"}) == constants.KNOWN_SDK_SETTING_SOURCES


def test_permission_profile_tables_self_consistent() -> None:
    """Each preset name appears in every resolution table; resolved
    SDK modes are all members of ``KNOWN_SDK_PERMISSION_MODES``."""
    assert set(constants.PERMISSION_PROFILE_TO_SDK_MODE) == constants.PERMISSION_PROFILE_NAMES
    assert set(constants.PERMISSION_PROFILE_ALLOWED_TOOLS) == constants.PERMISSION_PROFILE_NAMES
    assert set(constants.PERMISSION_PROFILE_DISALLOWED_TOOLS) == constants.PERMISSION_PROFILE_NAMES
    assert (
        set(constants.PERMISSION_PROFILE_TO_SDK_MODE.values())
        <= constants.KNOWN_SDK_PERMISSION_MODES
    )


def test_permission_profile_resolution_table_values() -> None:
    """Restricted asks for everything; standard auto-edits; expanded bypass."""
    assert constants.PERMISSION_PROFILE_TO_SDK_MODE["restricted"] == "default"
    assert constants.PERMISSION_PROFILE_TO_SDK_MODE["standard"] == "acceptEdits"
    assert constants.PERMISSION_PROFILE_TO_SDK_MODE["expanded"] == "bypassPermissions"


def test_restricted_profile_disallows_side_effecting_tools() -> None:
    """RESTRICTED carries explicit denies on Bash / Write / Edit."""
    denies = constants.PERMISSION_PROFILE_DISALLOWED_TOOLS["restricted"]
    assert "Bash" in denies
    assert "Write" in denies
    assert "Edit" in denies


def test_all_public_names_have_final_annotations() -> None:
    """Every name in ``__all__`` carries a ``Final[...]`` annotation.

    With ``from __future__ import annotations`` in the constants
    module, ``__annotations__`` holds the source-level string. Asserting
    ``"Final"`` substring is how we enforce the coding-standards
    directive that constants are typed-immutable.
    """
    annotations = constants.__annotations__
    for name in constants.__all__:
        assert hasattr(constants, name), f"{name!r} in __all__ but not defined"
        assert name in annotations, f"{name!r} has no annotation; constants must be Final[...]"
        assert "Final" in annotations[name], (
            f"{name!r} annotation {annotations[name]!r} is not Final[...]"
        )


def test_all_listed_in_alphabetical_order() -> None:
    """``__all__`` is sorted so future inserts have an obvious place."""
    assert constants.__all__ == sorted(constants.__all__)
