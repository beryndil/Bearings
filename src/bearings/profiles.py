"""Permission-profile presets for `bearings init <profile>`.

The 2026-04-21 security audit identified ten-ish gates that should
flip together as a posture choice rather than be reconfigured one at
a time. The presets here package those gates into three named
postures — `safe`, `workstation`, `power-user` — so a fresh install
can pick the right one in one decision.

The presets are *not* the source of truth for behavior. Each gate
remains an independent config knob (see `bearings.config`) and a
`bearings init` run materializes those knobs into `config.toml` as
ordinary keys. Mix-and-match works: an operator who picks `safe` and
then wants MCP back can edit one line in the TOML without losing the
rest of the posture. The profile's `name` field is recorded so the
startup banner can still announce the chosen baseline.

Intentional non-features:
- No "current profile" runtime state. The profile is the *snapshot*
  of decisions the user made when they ran `bearings init`. If they
  later edit individual knobs, the profile name still records what
  they started from — but the gates are whatever the TOML actually
  says, full stop.
- No precedence rules. Presets are flat key→value dicts that overwrite
  whatever was in the TOML before. We never merge half-old / half-new.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, get_args

from bearings.config import DATA_HOME, ProfileName

# Where the `safe` profile stashes per-session sandbox subdirs. Kept
# under `XDG_DATA_HOME` rather than `$HOME` so the operator can blow
# the whole tree away (`rm -rf ~/.local/share/bearings/workspaces`)
# without losing config or DB.
_SAFE_WORKSPACE_ROOT: Path = DATA_HOME / "workspaces"

# Conservative default ceiling on a `safe`-profile session. A runaway
# tool loop on Opus tops out near $1/turn in pathological cases; $5
# leaves room for several turns of legitimate work but caps the
# blast radius before any reasonable operator notices.
_SAFE_BUDGET_CEILING_USD = 5.0


def available_profiles() -> tuple[str, ...]:
    """The literal profile names accepted by `apply_profile`.

    Sourced from the `ProfileName` Literal so `--profile` argparse
    `choices=` and any UI dropdown stay in lockstep with the type."""
    return get_args(ProfileName)


def _generate_token() -> str:
    """Auto-generate an auth token for profiles that need one.

    `secrets.token_urlsafe(32)` ≈ 43 url-safe characters of 256-bit
    entropy. Long enough that brute-forcing over a localhost loopback
    in a useful timeframe is hopeless; short enough to fit on a
    terminal line for the operator to see in the banner."""
    return secrets.token_urlsafe(32)


def apply_profile(name: ProfileName) -> dict[str, Any]:
    """Return a nested config dict expressing the profile's gate choices.

    Output shape mirrors `Settings`'s `[section][key]` layout so it can
    be merged straight into `config.toml` data and round-tripped
    through `tomli_w.dump`. Sections that the profile doesn't touch
    are absent — caller is expected to start from an existing TOML
    (or empty dict) and overlay the profile's keys.

    Auth tokens are generated fresh on every call when the profile
    requires one, so re-running `bearings init safe` rotates the
    token. Operators who need a stable token should set it manually
    in TOML *after* the init run.
    """
    if name == "safe":
        return {
            "profile": {"name": "safe", "show_banner": True},
            "auth": {"enabled": True, "token": _generate_token()},
            "agent": {
                "workspace_root": str(_SAFE_WORKSPACE_ROOT),
                "default_max_budget_usd": _SAFE_BUDGET_CEILING_USD,
                "allow_bypass_permissions": False,
                "setting_sources": [],
                "inherit_mcp_servers": False,
                "inherit_hooks": False,
            },
            "fs": {"allow_root": str(_SAFE_WORKSPACE_ROOT)},
            "commands": {"scope": "project"},
            "runner": {"idle_ttl_seconds": 60.0},
        }
    if name == "workstation":
        return {
            "profile": {"name": "workstation", "show_banner": True},
            "auth": {"enabled": True, "token": _generate_token()},
            "agent": {
                # workstation runs from $HOME (today's default) but
                # opts back into per-call approval for Edit/Write —
                # bypassPermissions is allowed but ephemeral (the WS
                # selector still offers it; nothing persists it as the
                # default). The default permission mode stays at the
                # SDK default ("ask on every tool") so the operator
                # actively chooses to escalate per turn.
                "default_max_budget_usd": None,
                "allow_bypass_permissions": True,
                # `None` = SDK default, which inherits user/project/local
                # settings.json. workstation operators benefit from
                # their own ~/.claude/ workflow — not stripped.
                "setting_sources": None,
                "inherit_mcp_servers": True,
                "inherit_hooks": True,
            },
            # fs picker stays at $HOME (the FsCfg default), commands
            # palette includes user-level commands but skips plugins —
            # a middle-ground between "trust everything" and "trust
            # nothing".
            "commands": {"scope": "user"},
            "runner": {"idle_ttl_seconds": 900.0},
        }
    if name == "power-user":
        return {
            "profile": {"name": "power-user", "show_banner": True},
            # power-user is "today's defaults restored" — the only
            # write is the profile name so the banner can announce it.
            # We deliberately do NOT write auth/agent/etc. keys; the
            # operator is opting into raw defaults and any prior TOML
            # they had stays in place.
        }
    raise ValueError(f"unknown profile: {name!r}")


def merge_profile_into_toml(
    existing: dict[str, Any], profile_data: dict[str, Any]
) -> dict[str, Any]:
    """Overlay a profile's nested dict onto existing TOML data.

    Per-section keys in `profile_data` overwrite the same keys in
    `existing`; sibling keys the profile doesn't touch survive
    untouched. We do NOT recurse beyond the section level — every
    config section in Bearings is currently a flat key=value table,
    and treating them that way keeps the merge predictable. If a
    future config section adds a deeply-nested table (none today),
    this helper grows a recursion check.
    """
    merged: dict[str, Any] = dict(existing)
    for section, values in profile_data.items():
        if isinstance(values, dict) and isinstance(merged.get(section), dict):
            merged[section] = {**merged[section], **values}
        else:
            merged[section] = values
    return merged
