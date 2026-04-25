"""Tests for the permission-profile preset layer.

Pins the gates each profile flips and the merge semantics that make
mix-and-match practical (operator picks `safe`, then keeps a hand-
edited config knob the profile doesn't touch).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
import tomli_w

from bearings.cli import (
    _format_gate_state,
    _print_profile_banner,
    _write_profile,
)
from bearings.config import Settings, load_settings
from bearings.profiles import (
    apply_profile,
    available_profiles,
    merge_profile_into_toml,
)


def test_available_profiles_matches_literal() -> None:
    """`available_profiles()` is what `argparse` and any UI dropdown
    consume. The literal in `config.ProfileName` is the source of
    truth — adding a new profile must lift through this tuple
    automatically."""
    assert set(available_profiles()) == {"safe", "workstation", "power-user"}


def test_apply_safe_profile_locks_down_gates() -> None:
    """The `safe` profile is the public-default posture. Every gate
    that the 2026-04-21 audit identified must be in its closed
    position: auth on, sandboxed working_dir, no Claude config
    inherit, no MCP / hooks, bypassPermissions blocked, project-only
    commands palette, default budget ceiling. Regression here is a
    silent posture downgrade for every fresh public install."""
    data = apply_profile("safe")
    assert data["profile"]["name"] == "safe"
    assert data["auth"]["enabled"] is True
    # Auth token is non-empty + reasonably long. We don't pin a
    # specific length — `secrets.token_urlsafe(32)` length is an
    # implementation detail — but a short / empty token would be a
    # red flag.
    assert isinstance(data["auth"]["token"], str)
    assert len(data["auth"]["token"]) >= 32
    agent = data["agent"]
    assert agent["allow_bypass_permissions"] is False
    assert agent["setting_sources"] == []
    assert agent["inherit_mcp_servers"] is False
    assert agent["inherit_hooks"] is False
    assert agent["default_max_budget_usd"] is not None
    assert "workspaces" in agent["workspace_root"]
    assert data["fs"]["allow_root"] == agent["workspace_root"]
    assert data["commands"]["scope"] == "project"


def test_apply_workstation_profile_keeps_inherits_open() -> None:
    """`workstation` is the laptop default — auth on, but MCP / hooks
    / Claude settings inherit are intentionally permissive because the
    operator wants their `~/.claude/` workflow to apply. Regression
    here means a workstation operator silently loses their MCP
    servers when they pick the profile."""
    data = apply_profile("workstation")
    assert data["profile"]["name"] == "workstation"
    assert data["auth"]["enabled"] is True
    agent = data["agent"]
    assert agent["allow_bypass_permissions"] is True
    assert agent["inherit_mcp_servers"] is True
    assert agent["inherit_hooks"] is True
    assert agent["setting_sources"] is None  # SDK-default inherit
    assert "workspace_root" not in agent  # $HOME default kept
    assert data["commands"]["scope"] == "user"


def test_apply_power_user_profile_only_records_name() -> None:
    """`power-user` is "today's defaults restored." The preset must
    not write any concrete gate keys — that's what makes it a no-op
    on existing installs. Only the profile name is recorded so the
    banner can announce it."""
    data = apply_profile("power-user")
    assert data == {"profile": {"name": "power-user", "show_banner": True}}


def test_apply_unknown_profile_raises() -> None:
    """Anything outside the `ProfileName` literal must raise so a
    typo at the CLI surface fails loudly."""
    with pytest.raises(ValueError, match="unknown profile"):
        apply_profile("nope")  # type: ignore[arg-type]


def test_safe_profile_rotates_token_per_apply() -> None:
    """Re-running `bearings init safe` should produce a fresh token
    every time. Operators who want stability set the token manually
    in TOML after init — the helper itself never reuses one."""
    a = apply_profile("safe")["auth"]["token"]
    b = apply_profile("safe")["auth"]["token"]
    assert a != b


def test_merge_profile_overlays_existing_toml() -> None:
    """Profile keys overwrite same-key existing values; sibling keys
    the profile doesn't touch survive untouched. This is what makes
    mix-and-match work — operator picks safe, then keeps their
    hand-edited `[runner].reap_interval_seconds`."""
    existing = {
        "server": {"port": 9090},
        "runner": {"reap_interval_seconds": 5.0, "idle_ttl_seconds": 999.0},
        "billing": {"mode": "subscription"},
    }
    merged = merge_profile_into_toml(existing, apply_profile("safe"))
    # Untouched section stays.
    assert merged["server"]["port"] == 9090
    assert merged["billing"]["mode"] == "subscription"
    # Profile overlay landed.
    assert merged["auth"]["enabled"] is True
    # In-section: overlapping key wins for the profile, sibling keys
    # in the same section survive.
    assert merged["runner"]["idle_ttl_seconds"] == 60.0
    assert merged["runner"]["reap_interval_seconds"] == 5.0


def test_write_profile_round_trips_via_load_settings(tmp_path: Path) -> None:
    """End-to-end: write a profile to disk, load_settings reads it
    back and the resulting `Settings` reflects the gates. The format
    on disk must be the format pydantic-settings can parse without a
    nudge — the round-trip catches any TOML serialization bug that
    would only surface in production."""
    config_path = tmp_path / "config.toml"
    _write_profile(config_path, "safe")
    cfg = load_settings(config_path)
    assert cfg.profile.name == "safe"
    assert cfg.auth.enabled is True
    assert cfg.agent.allow_bypass_permissions is False
    assert cfg.agent.inherit_mcp_servers is False
    assert cfg.agent.inherit_hooks is False
    assert cfg.agent.setting_sources == []
    assert cfg.commands.scope == "project"


def test_write_profile_preserves_unrelated_existing_keys(tmp_path: Path) -> None:
    """Operator may have a pre-existing `config.toml` with custom
    knobs. `bearings init --profile safe` must overlay, not clobber
    — sibling keys the profile doesn't touch survive."""
    config_path = tmp_path / "config.toml"
    with config_path.open("wb") as fh:
        tomli_w.dump(
            {
                "server": {"port": 9999},
                "runner": {"reap_interval_seconds": 7.0},
            },
            fh,
        )
    _write_profile(config_path, "safe")
    cfg = load_settings(config_path)
    assert cfg.server.port == 9999
    assert cfg.runner.reap_interval_seconds == 7.0
    # Profile gates landed.
    assert cfg.profile.name == "safe"
    assert cfg.auth.enabled is True


def test_format_gate_state_lists_every_audit_axis() -> None:
    """The banner is the operator's single-glance posture audit.
    Every gate that an attacker could exploit if it were open must
    have a visible line — auth, bypass, settings inherit, MCP, hooks,
    working_dir / sandbox, budget cap, fs root, commands scope, idle
    TTL, bind. Regression here means a gate quietly opens without the
    operator noticing."""
    cfg = Settings()
    lines = "\n".join(_format_gate_state(cfg))
    for needle in (
        "auth ",
        "bypassPermissions",
        "settings inherit",
        "MCP servers",
        "hooks inherited",
        "budget cap",
        "fs picker root",
        "commands palette scope",
        "runner idle TTL",
        "bind ",
    ):
        assert needle in lines, f"banner audit missing axis: {needle!r}"


def test_print_profile_banner_announces_active_name() -> None:
    """Operator restarts the server; the banner must lead with which
    profile they're running so they can verify the posture before
    the first request lands."""
    cfg = Settings(profile={"name": "safe", "show_banner": True})  # type: ignore[arg-type]
    out = io.StringIO()
    _print_profile_banner(cfg, fh=out)
    text = out.getvalue()
    assert "permission profile: safe" in text


def test_print_profile_banner_handles_no_profile() -> None:
    """An operator who skipped `bearings init --profile X` runs raw
    defaults. The banner must still print but disclose that no profile
    is in effect — silence would be worse than a confused operator."""
    cfg = Settings()
    out = io.StringIO()
    _print_profile_banner(cfg, fh=out)
    text = out.getvalue()
    assert "raw defaults" in text or "(none" in text
