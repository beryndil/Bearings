"""Permission-profile tests for :class:`bearings.agent.session.AgentSession`.

The three profiles (RESTRICTED / STANDARD / EXPANDED) resolve to an
SDK ``permission_mode`` + ``allowed_tools`` + ``disallowed_tools``
triple via constant tables. Tests verify:

* the enum members match the constants-module name set;
* each profile resolves to the documented SDK permission_mode;
* each profile resolves to the documented allowed_tools list;
* RESTRICTED carries explicit denies on side-effecting tools;
* explicit :attr:`SessionConfig.permission_mode` overrides the
  profile's resolved mode (more-specific wins).
"""

from __future__ import annotations

from bearings.agent.routing import RoutingDecision
from bearings.agent.session import (
    AgentSession,
    PermissionProfile,
    SessionConfig,
)
from bearings.config import constants


def _decision() -> RoutingDecision:
    return RoutingDecision(
        executor_model="sonnet",
        advisor_model="opus",
        advisor_max_uses=5,
        effort_level="auto",
        source="default",
        reason="permission profile test",
        matched_rule_id=None,
    )


def _make_session(*, profile: PermissionProfile, mode: str | None = None) -> AgentSession:
    return AgentSession(
        SessionConfig(
            session_id="sess-1",
            working_dir="/tmp/profiles",
            decision=_decision(),
            db=None,
            permission_profile=profile,
            permission_mode=mode,
        )
    )


# ---------------------------------------------------------------------------
# Enum / table membership
# ---------------------------------------------------------------------------


def test_profile_enum_members_match_constants() -> None:
    """The enum and the constants-module table must agree on names."""
    assert {p.value for p in PermissionProfile} == constants.PERMISSION_PROFILE_NAMES


def test_default_profile_is_standard() -> None:
    """STANDARD is the day-to-day default — matches v0.17.x's
    effective behaviour of running with ``acceptEdits``."""
    sess = AgentSession(
        SessionConfig(
            session_id="sess-1",
            working_dir="/tmp/x",
            decision=_decision(),
            db=None,
        )
    )
    assert sess.config.permission_profile is PermissionProfile.STANDARD


# ---------------------------------------------------------------------------
# Profile → SDK mode resolution
# ---------------------------------------------------------------------------


def test_restricted_profile_resolves_to_default_mode() -> None:
    sess = _make_session(profile=PermissionProfile.RESTRICTED)
    assert sess.effective_permission_mode() == "default"


def test_standard_profile_resolves_to_accept_edits() -> None:
    sess = _make_session(profile=PermissionProfile.STANDARD)
    assert sess.effective_permission_mode() == "acceptEdits"


def test_expanded_profile_resolves_to_bypass_permissions() -> None:
    sess = _make_session(profile=PermissionProfile.EXPANDED)
    assert sess.effective_permission_mode() == "bypassPermissions"


def test_explicit_permission_mode_overrides_profile() -> None:
    """``SessionConfig.permission_mode`` is the more-specific override
    and wins over the profile's resolved mode."""
    sess = _make_session(profile=PermissionProfile.RESTRICTED, mode="plan")
    assert sess.effective_permission_mode() == "plan"


def test_explicit_permission_mode_overrides_standard_profile() -> None:
    sess = _make_session(profile=PermissionProfile.STANDARD, mode="dontAsk")
    assert sess.effective_permission_mode() == "dontAsk"


# ---------------------------------------------------------------------------
# Profile → allowed_tools / disallowed_tools resolution
# ---------------------------------------------------------------------------


def test_restricted_profile_disallows_side_effecting_tools() -> None:
    sess = _make_session(profile=PermissionProfile.RESTRICTED)
    denies = sess.effective_disallowed_tools()
    assert "Bash" in denies
    assert "Write" in denies
    assert "Edit" in denies


def test_restricted_profile_allows_read_only_tools() -> None:
    sess = _make_session(profile=PermissionProfile.RESTRICTED)
    allowed = sess.effective_allowed_tools()
    assert "Read" in allowed
    assert "Glob" in allowed
    assert "Grep" in allowed
    # No Bash / Write / Edit in the allow list either.
    assert "Bash" not in allowed
    assert "Write" not in allowed
    assert "Edit" not in allowed


def test_standard_profile_allows_edits() -> None:
    sess = _make_session(profile=PermissionProfile.STANDARD)
    allowed = sess.effective_allowed_tools()
    assert "Read" in allowed
    assert "Write" in allowed
    assert "Edit" in allowed
    assert "Bash" in allowed
    # STANDARD does not carry explicit denies — delegates to acceptEdits.
    assert sess.effective_disallowed_tools() == ()


def test_expanded_profile_widens_to_empty_lists() -> None:
    """Per the constants-module note, EXPANDED has empty allow + deny
    lists because ``bypassPermissions`` auto-approves at the SDK
    boundary."""
    sess = _make_session(profile=PermissionProfile.EXPANDED)
    assert sess.effective_allowed_tools() == ()
    assert sess.effective_disallowed_tools() == ()


# ---------------------------------------------------------------------------
# Cross-table consistency
# ---------------------------------------------------------------------------


def test_each_profile_has_a_resolution_for_every_method() -> None:
    """Every profile resolves successfully for all three resolver
    methods; no profile silently falls back to a default."""
    for profile in PermissionProfile:
        sess = _make_session(profile=profile)
        # Each call returns a non-None value of the right type.
        assert isinstance(sess.effective_permission_mode(), str)
        assert isinstance(sess.effective_allowed_tools(), tuple)
        assert isinstance(sess.effective_disallowed_tools(), tuple)


def test_resolved_modes_are_known_sdk_modes() -> None:
    """Every profile's resolved SDK mode is in the SDK's literal alphabet."""
    for profile in PermissionProfile:
        sess = _make_session(profile=profile)
        assert sess.effective_permission_mode() in constants.KNOWN_SDK_PERMISSION_MODES
