"""Tests for :mod:`bearings.config.settings`.

Coverage matches the item-0.5 done-when test list:

* ``Settings()`` with no env vars + no TOML file → defaults match
  constants.
* TOML file at the XDG path → values override defaults.
* Env vars present → override TOML.
* Invalid TOML key → ``ValidationError`` (``extra="forbid"``).
* Invalid type (e.g. ``BEARINGS_PORT=not-an-int``) → ``ValidationError``.

Plus precedence (kwargs > env > TOML), case-insensitive env-var
matching, and the XDG fallback when ``XDG_CONFIG_HOME`` is unset.

The autouse fixture isolates every test from the developer's actual
environment by pointing ``XDG_CONFIG_HOME`` at a per-test tmp dir and
clearing every ``BEARINGS_*`` env var the shell may have inherited.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from bearings.config import Settings, xdg_config_path
from bearings.config.constants import (
    DEFAULT_DB_PATH,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_TOOL_OUTPUT_CAP_CHARS,
    OVERRIDE_RATE_REVIEW_THRESHOLD,
    QUOTA_THRESHOLD_PCT,
    ROUTING_PREVIEW_DEBOUNCE_MS,
    USAGE_POLL_INTERVAL_S,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point XDG_CONFIG_HOME at an isolated tmp dir; clear BEARINGS_* vars.

    Without this fixture, a developer's real ``~/.config/bearings/
    config.toml`` or shell-exported ``BEARINGS_*`` overrides would leak
    into every test and produce nondeterministic failures.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for var in list(os.environ):
        if var.startswith("BEARINGS_"):
            monkeypatch.delenv(var, raising=False)


def _write_toml(tmp_path: Path, body: str) -> Path:
    """Create the XDG-resolved config file with the given body and return its path."""
    cfg_dir = tmp_path / "bearings"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / "config.toml"
    cfg_file.write_text(body, encoding="utf-8")
    return cfg_file


def test_defaults_with_no_overrides() -> None:
    """No env vars + no TOML file → every default matches the constants module."""
    settings = Settings()
    assert settings.port == DEFAULT_PORT
    assert settings.host == DEFAULT_HOST
    assert settings.db_path == DEFAULT_DB_PATH
    assert settings.tool_output_cap_chars == DEFAULT_TOOL_OUTPUT_CAP_CHARS
    assert settings.routing_preview_debounce_ms == ROUTING_PREVIEW_DEBOUNCE_MS
    assert settings.advisor_enabled is True
    assert settings.quota_threshold_pct == QUOTA_THRESHOLD_PCT
    assert settings.quota_poll_interval_s == USAGE_POLL_INTERVAL_S
    assert settings.override_rate_review_threshold == OVERRIDE_RATE_REVIEW_THRESHOLD


def test_xdg_config_path_uses_xdg_config_home(tmp_path: Path) -> None:
    """The fixture set XDG_CONFIG_HOME=tmp_path; xdg_config_path appends 'bearings/config.toml'."""
    assert xdg_config_path() == tmp_path / "bearings" / "config.toml"


def test_xdg_config_path_falls_back_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unset XDG_CONFIG_HOME falls back to ``~/.config`` per the XDG spec."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert xdg_config_path() == Path("~/.config").expanduser() / "bearings" / "config.toml"


def test_xdg_config_path_falls_back_when_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    """A whitespace-only XDG_CONFIG_HOME falls back per the XDG spec."""
    monkeypatch.setenv("XDG_CONFIG_HOME", "   ")
    assert xdg_config_path() == Path("~/.config").expanduser() / "bearings" / "config.toml"


def test_toml_overrides_defaults(tmp_path: Path) -> None:
    """Values written to the XDG config file override the constants-backed defaults."""
    _write_toml(
        tmp_path,
        body=('port = 9001\nhost = "0.0.0.0"\nadvisor_enabled = false\n'),
    )
    settings = Settings()
    assert settings.port == 9001
    assert settings.host == "0.0.0.0"
    assert settings.advisor_enabled is False
    # Untouched fields keep the default.
    assert settings.tool_output_cap_chars == DEFAULT_TOOL_OUTPUT_CAP_CHARS


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Env vars take precedence over the TOML file for the same key."""
    _write_toml(tmp_path, body="port = 9001\n")
    monkeypatch.setenv("BEARINGS_PORT", "9999")
    assert Settings().port == 9999


def test_kwargs_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Constructor kwargs (used by tests) take precedence over env vars."""
    monkeypatch.setenv("BEARINGS_PORT", "9999")
    assert Settings(port=8888).port == 8888


def test_invalid_toml_key_rejected(tmp_path: Path) -> None:
    """``extra='forbid'`` rejects unknown TOML keys (typo guard)."""
    _write_toml(tmp_path, body='not_a_real_setting = "x"\n')
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_env_var_type_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Type-coercion failures from env vars surface as ValidationError, not silent fallback."""
    monkeypatch.setenv("BEARINGS_PORT", "not-an-int")
    with pytest.raises(ValidationError):
        Settings()


def test_port_out_of_range_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Port range constraint (1-65535) is enforced."""
    monkeypatch.setenv("BEARINGS_PORT", "0")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("BEARINGS_PORT", "70000")
    with pytest.raises(ValidationError):
        Settings()


def test_quota_threshold_out_of_range_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Quota threshold must lie in [0.0, 1.0]."""
    monkeypatch.setenv("BEARINGS_QUOTA_THRESHOLD_PCT", "1.5")
    with pytest.raises(ValidationError):
        Settings()


def test_case_insensitive_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lowercase env-var names match the same field as uppercase."""
    monkeypatch.setenv("bearings_port", "9000")
    assert Settings().port == 9000


def test_db_path_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``BEARINGS_DB_PATH`` resolves directly to the ``db_path`` field."""
    target = tmp_path / "custom" / "sessions.db"
    monkeypatch.setenv("BEARINGS_DB_PATH", str(target))
    settings = Settings()
    assert settings.db_path == target


def test_no_toml_file_still_produces_defaults(tmp_path: Path) -> None:
    """A missing config file is silently treated as 'no overrides' — not an error.

    The XDG dir under ``tmp_path`` is fresh (no ``bearings/`` subdir).
    pydantic-settings' ``TomlConfigSettingsSource`` documents this
    behaviour; the test pins it explicitly so a future refactor that
    inadvertently raises here surfaces.
    """
    settings = Settings()
    assert settings.port == DEFAULT_PORT
    assert settings.db_path == DEFAULT_DB_PATH


def test_unknown_env_var_silently_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """pydantic-settings filters env vars to known fields BEFORE ``extra='forbid'`` runs.

    Pinned as documented behaviour: ``BEARINGS_*`` env vars that do not
    match a field name are silently ignored (the env source never
    presents them to the validator). The ``extra='forbid'`` gate still
    fires for *TOML* keys, where every key is passed through — see
    :func:`test_invalid_toml_key_rejected`. Asymmetry is by design in
    pydantic-settings 2.x; pinning it here surfaces any future change.
    """
    monkeypatch.setenv("BEARINGS_NOT_A_REAL_SETTING", "x")
    settings = Settings()
    # Surviving without raising is the assertion; defaults still hold.
    assert settings.port == DEFAULT_PORT
