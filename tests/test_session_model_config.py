"""Model-config validation tests for :class:`bearings.agent.session.SessionConfig`
and the embedded :class:`bearings.agent.routing.RoutingDecision`.

Covers the Done-when test surface: known-model accept / unknown-model
reject; advisor-with-zero-uses round-tripping; effort levels
enumerated; routing source enum guard; setting_sources literal
alphabet enforced; positive-only ``tool_output_cap_chars``;
non-negative ``max_budget_usd``; non-empty session_id / working_dir.

The test for "advisor model + executor model both required when
advisor_enabled" is handled implicitly: ``executor_model`` is always
required (an empty value raises), so any decision with an advisor
also has an executor. We additionally assert that an unknown advisor
short name is rejected.
"""

from __future__ import annotations

import pytest

from bearings.agent.routing import RoutingDecision
from bearings.agent.session import (
    PermissionProfile,
    SessionConfig,
)
from bearings.config import constants


def _decision(**overrides: object) -> RoutingDecision:
    """Build a default-shaped RoutingDecision with field overrides."""
    base: dict[str, object] = {
        "executor_model": "sonnet",
        "advisor_model": "opus",
        "advisor_max_uses": 5,
        "effort_level": "auto",
        "source": "default",
        "reason": "test",
        "matched_rule_id": None,
    }
    base.update(overrides)
    return RoutingDecision(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# RoutingDecision validation
# ---------------------------------------------------------------------------


def test_routing_decision_accepts_known_short_names() -> None:
    for name in ("sonnet", "haiku", "opus", "opusplan"):
        decision = _decision(executor_model=name)
        assert decision.executor_model == name


def test_routing_decision_accepts_full_sdk_id() -> None:
    """Any string starting with ``claude-`` passes (per arch §5 #4 +
    constants.EXECUTOR_MODEL_FULL_ID_PREFIX)."""
    decision = _decision(executor_model="claude-sonnet-4-5")
    assert decision.executor_model == "claude-sonnet-4-5"


def test_routing_decision_rejects_unknown_executor() -> None:
    with pytest.raises(ValueError, match="executor_model"):
        _decision(executor_model="sonet")  # typo


def test_routing_decision_rejects_empty_executor() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        _decision(executor_model="")


def test_routing_decision_rejects_unknown_advisor() -> None:
    with pytest.raises(ValueError, match="advisor_model"):
        _decision(advisor_model="oppus")


def test_routing_decision_accepts_no_advisor() -> None:
    """Per spec App A: ``advisor_model`` may be ``None``."""
    decision = _decision(advisor_model=None, advisor_max_uses=0)
    assert decision.advisor_model is None


def test_routing_decision_rejects_unknown_effort() -> None:
    with pytest.raises(ValueError, match="effort_level"):
        _decision(effort_level="ultra")


def test_routing_decision_accepts_every_known_effort() -> None:
    for level in constants.KNOWN_EFFORT_LEVELS:
        d = _decision(effort_level=level)
        assert d.effort_level == level


def test_routing_decision_rejects_negative_advisor_uses() -> None:
    with pytest.raises(ValueError, match="advisor_max_uses"):
        _decision(advisor_max_uses=-1)


def test_routing_decision_advisor_zero_uses_with_advisor_model_allowed() -> None:
    """``advisor_max_uses=0`` with a non-None advisor_model is the
    "declared but unused this turn" carry-through shape."""
    d = _decision(advisor_model="opus", advisor_max_uses=0)
    assert d.advisor_max_uses == 0


def test_routing_decision_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="source"):
        _decision(source="some_other_source")


def test_routing_decision_accepts_every_known_source() -> None:
    for src in constants.KNOWN_ROUTING_SOURCES:
        d = _decision(source=src)
        assert d.source == src


def test_routing_decision_quota_state_default_empty() -> None:
    d = _decision()
    assert d.quota_state_at_decision == {}
    assert d.evaluated_rules == []


# ---------------------------------------------------------------------------
# SessionConfig validation
# ---------------------------------------------------------------------------


def test_session_config_minimal_construction() -> None:
    cfg = SessionConfig(
        session_id="s-1",
        working_dir="/tmp/x",
        decision=_decision(),
        db=None,
    )
    assert cfg.session_id == "s-1"
    assert cfg.working_dir == "/tmp/x"
    assert cfg.permission_profile is PermissionProfile.STANDARD
    assert cfg.permission_mode is None
    assert cfg.tool_output_cap_chars == constants.DEFAULT_TOOL_OUTPUT_CAP_CHARS
    assert cfg.inherit_mcp_servers is True
    assert cfg.inherit_hooks is True
    assert cfg.enable_bearings_mcp is True
    assert cfg.enable_precompact_steering is True
    assert cfg.enable_researcher_subagent is False


def test_session_config_session_id_non_empty() -> None:
    with pytest.raises(ValueError, match="session_id"):
        SessionConfig(
            session_id="",
            working_dir="/tmp/x",
            decision=_decision(),
            db=None,
        )


def test_session_config_working_dir_non_empty() -> None:
    with pytest.raises(ValueError, match="working_dir"):
        SessionConfig(
            session_id="s-1",
            working_dir="",
            decision=_decision(),
            db=None,
        )


def test_session_config_tool_output_cap_must_be_positive() -> None:
    with pytest.raises(ValueError, match="tool_output_cap_chars"):
        SessionConfig(
            session_id="s-1",
            working_dir="/tmp/x",
            decision=_decision(),
            db=None,
            tool_output_cap_chars=0,
        )


def test_session_config_tool_output_cap_negative_rejected() -> None:
    with pytest.raises(ValueError, match="tool_output_cap_chars"):
        SessionConfig(
            session_id="s-1",
            working_dir="/tmp/x",
            decision=_decision(),
            db=None,
            tool_output_cap_chars=-1,
        )


def test_session_config_max_budget_negative_rejected() -> None:
    with pytest.raises(ValueError, match="max_budget_usd"):
        SessionConfig(
            session_id="s-1",
            working_dir="/tmp/x",
            decision=_decision(),
            db=None,
            max_budget_usd=-0.01,
        )


def test_session_config_max_budget_zero_allowed() -> None:
    """A zero budget is the spec's "PAYG cap = 0 means stop on cost"
    semantic; not negative, so accepted."""
    cfg = SessionConfig(
        session_id="s-1",
        working_dir="/tmp/x",
        decision=_decision(),
        db=None,
        max_budget_usd=0.0,
    )
    assert cfg.max_budget_usd == 0.0


def test_session_config_unknown_permission_mode_rejected() -> None:
    with pytest.raises(ValueError, match="permission_mode"):
        SessionConfig(
            session_id="s-1",
            working_dir="/tmp/x",
            decision=_decision(),
            db=None,
            permission_mode="bogus_mode",
        )


def test_session_config_every_known_permission_mode_accepted() -> None:
    for mode in constants.KNOWN_SDK_PERMISSION_MODES:
        cfg = SessionConfig(
            session_id="s-1",
            working_dir="/tmp/x",
            decision=_decision(),
            db=None,
            permission_mode=mode,
        )
        assert cfg.permission_mode == mode


def test_session_config_unknown_setting_source_rejected() -> None:
    with pytest.raises(ValueError, match="setting_sources"):
        SessionConfig(
            session_id="s-1",
            working_dir="/tmp/x",
            decision=_decision(),
            db=None,
            setting_sources=("user", "global"),
        )


def test_session_config_known_setting_sources_accepted() -> None:
    cfg = SessionConfig(
        session_id="s-1",
        working_dir="/tmp/x",
        decision=_decision(),
        db=None,
        setting_sources=("user", "project", "local"),
    )
    assert cfg.setting_sources == ("user", "project", "local")


def test_session_config_is_frozen() -> None:
    """Per arch §4.8 SessionConfig is a frozen dataclass."""
    cfg = SessionConfig(
        session_id="s-1",
        working_dir="/tmp/x",
        decision=_decision(),
        db=None,
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        cfg.session_id = "s-2"  # type: ignore[misc]


def test_session_config_carries_executor_advisor_effort() -> None:
    """Spec compliance: SessionConfig.decision carries executor + advisor +
    effort (the three required routing-aware fields per spec §App A)."""
    decision = _decision(
        executor_model="sonnet",
        advisor_model="opus",
        advisor_max_uses=5,
        effort_level="high",
    )
    cfg = SessionConfig(
        session_id="s-1",
        working_dir="/tmp/x",
        decision=decision,
        db=None,
    )
    assert cfg.decision.executor_model == "sonnet"
    assert cfg.decision.advisor_model == "opus"
    assert cfg.decision.advisor_max_uses == 5
    assert cfg.decision.effort_level == "high"
