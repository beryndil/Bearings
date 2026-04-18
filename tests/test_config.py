from __future__ import annotations

from pathlib import Path

from twrminal.config import Settings, load_settings


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
