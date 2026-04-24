from __future__ import annotations

from pathlib import Path

from bearings.cli import _check_bind_auth_interlock
from bearings.config import AuthCfg, ServerCfg, Settings, load_settings


def test_defaults_are_localhost() -> None:
    cfg = Settings()
    assert cfg.server.host == "127.0.0.1"
    assert cfg.server.port == 8787
    assert cfg.auth.enabled is False


def test_load_settings_accepts_missing_file(tmp_path: Path) -> None:
    cfg = load_settings(tmp_path / "absent.toml")
    assert cfg.config_file == tmp_path / "absent.toml"
    assert cfg.server.port == 8787


def test_load_settings_parses_toml(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[server]\nport = 9090\n")
    cfg = load_settings(path)
    assert cfg.server.port == 9090


def test_agent_thinking_defaults_to_adaptive() -> None:
    """Default agent.thinking is `adaptive` so the UI shows reasoning
    out of the box without a config-file nudge. A regression here
    means new sessions silently lose extended thinking."""
    cfg = Settings()
    assert cfg.agent.thinking == "adaptive"


def test_agent_thinking_can_be_disabled(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[agent]\nthinking = "disabled"\n')
    cfg = load_settings(path)
    assert cfg.agent.thinking == "disabled"


def test_agent_thinking_accepts_none() -> None:
    """`None` skips the flag entirely and lets the SDK's own default
    apply. TOML has no null literal, so this path is only reachable
    via the BaseSettings constructor — but the default-handling branch
    in `_thinking_config` needs a passing-case to keep working."""
    cfg = Settings(agent={"thinking": None})  # type: ignore[arg-type]
    assert cfg.agent.thinking is None


def test_billing_defaults_to_payg() -> None:
    """The default billing mode is `payg` so developer-API users who
    were already running Bearings see the exact same dollar display
    after the subscription-mode knob lands. A regression here means
    their session cards suddenly hide cost figures."""
    cfg = Settings()
    assert cfg.billing.mode == "payg"
    assert cfg.billing.plan is None


def test_billing_accepts_subscription_mode(tmp_path: Path) -> None:
    """Max/Pro subscribers flip `billing.mode = "subscription"` in
    config.toml to swap the dollar meter for token totals. The
    frontend keys off this exact string, so it must round-trip
    through pydantic intact."""
    path = tmp_path / "config.toml"
    path.write_text('[billing]\nmode = "subscription"\nplan = "max_20x"\n')
    cfg = load_settings(path)
    assert cfg.billing.mode == "subscription"
    assert cfg.billing.plan == "max_20x"


# ---- bind/auth interlock (2026-04-21 security audit §6) ------------


def test_interlock_allows_loopback_without_auth() -> None:
    """Default config (127.0.0.1, auth off) is the localhost-only
    developer flow. Interlock must not trip here."""
    cfg = Settings()
    assert _check_bind_auth_interlock(cfg) is None


def test_interlock_allows_loopback_aliases_without_auth() -> None:
    """`localhost` and `::1` are just as loopback as `127.0.0.1`;
    the interlock must treat them the same."""
    for host in ("localhost", "::1", "::ffff:127.0.0.1"):
        cfg = Settings(server=ServerCfg(host=host))
        assert _check_bind_auth_interlock(cfg) is None, f"{host!r} should be loopback"


def test_interlock_refuses_wildcard_bind_without_auth() -> None:
    """`0.0.0.0` + auth off is the bug this interlock exists to catch."""
    cfg = Settings(server=ServerCfg(host="0.0.0.0"), auth=AuthCfg(enabled=False))
    err = _check_bind_auth_interlock(cfg)
    assert err is not None
    assert "0.0.0.0" in err
    assert "auth.enabled" in err


def test_interlock_refuses_lan_bind_without_auth() -> None:
    """A specific LAN address is also non-loopback; the interlock
    shouldn't only look at the wildcard form."""
    cfg = Settings(server=ServerCfg(host="192.168.1.50"), auth=AuthCfg(enabled=False))
    assert _check_bind_auth_interlock(cfg) is not None


def test_interlock_allows_wildcard_bind_when_auth_configured() -> None:
    """Operator deliberately exposing the UI + supplying a token is
    a legitimate reverse-proxy scenario — don't block it."""
    cfg = Settings(
        server=ServerCfg(host="0.0.0.0"),
        auth=AuthCfg(enabled=True, token="s3cret"),
    )
    assert _check_bind_auth_interlock(cfg) is None


def test_interlock_refuses_non_loopback_with_auth_enabled_but_empty_token() -> None:
    """`auth.enabled=true` with no token is the config-error path the
    require_auth side also refuses. Interlock mirrors it: an empty
    token doesn't count as "auth configured"."""
    cfg = Settings(
        server=ServerCfg(host="0.0.0.0"),
        auth=AuthCfg(enabled=True, token=None),
    )
    assert _check_bind_auth_interlock(cfg) is not None


def test_default_max_budget_usd_defaults_to_none() -> None:
    """Today's behavior: no global cap until the operator sets one."""
    cfg = Settings()
    assert cfg.agent.default_max_budget_usd is None


def test_default_max_budget_usd_accepts_positive_float(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[agent]\ndefault_max_budget_usd = 2.50\n")
    cfg = load_settings(path)
    assert cfg.agent.default_max_budget_usd == 2.50


def test_commands_scope_defaults_to_all() -> None:
    """Keep today's behavior the default: `safe` profile flips it."""
    cfg = Settings()
    assert cfg.commands.scope == "all"


def test_commands_scope_accepts_project(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[commands]\nscope = "project"\n')
    cfg = load_settings(path)
    assert cfg.commands.scope == "project"
