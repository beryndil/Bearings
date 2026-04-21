from __future__ import annotations

from pathlib import Path

from bearings.config import Settings, load_settings


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
