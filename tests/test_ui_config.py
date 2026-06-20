"""Tests for GET /api/ui-config."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from bearings.config.constants import DEFAULT_BILLING_MODE
from bearings.web.app import create_app


def test_ui_config_response_shape() -> None:
    """GET /api/ui-config returns all required top-level keys."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/ui-config")
    assert resp.status_code == 200
    body = resp.json()
    assert "commands_scope" in body
    assert "billing_mode" in body
    assert "feature_flags" in body


def test_ui_config_feature_flags_shape() -> None:
    """feature_flags contains the expected boolean keys."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/ui-config")
    flags = resp.json()["feature_flags"]
    assert isinstance(flags, dict)
    assert "reply_actions" in flags
    assert "artifacts" in flags
    assert "analytics" in flags
    assert "spawn_from_reply" in flags
    for key, val in flags.items():
        assert isinstance(val, bool), f"flag {key!r} should be bool, got {type(val)}"


def test_ui_config_billing_mode_default() -> None:
    """billing_mode defaults to DEFAULT_BILLING_MODE when app built without config."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/ui-config")
    assert resp.json()["billing_mode"] == DEFAULT_BILLING_MODE


def test_ui_config_billing_mode_from_app_state() -> None:
    """billing_mode reflects the value set on app.state by create_app."""
    app = create_app(billing_mode="subscription")
    with TestClient(app) as client:
        resp = client.get("/api/ui-config")
    assert resp.json()["billing_mode"] == "subscription"


def test_ui_config_commands_scope_is_string() -> None:
    """commands_scope is a non-empty string."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/ui-config")
    scope = resp.json()["commands_scope"]
    assert isinstance(scope, str) and scope


# ---- N-13: context_menus field -----------------------------------------------


def test_ui_config_context_menus_default_empty() -> None:
    """context_menus defaults to empty pin/hide when menus.toml is absent."""
    app = create_app()
    # Patch Path.exists to simulate no menus.toml on disk.
    with patch.object(Path, "exists", return_value=False), TestClient(app) as client:
        resp = client.get("/api/ui-config")
    body = resp.json()
    assert "context_menus" in body
    cm = body["context_menus"]
    assert cm["pin"] == []
    assert cm["hide"] == []


def test_ui_config_context_menus_loaded_from_toml(tmp_path: Path) -> None:
    """context_menus.pin / hide are loaded from ~/.config/bearings/menus.toml."""
    # Create the full path the loader expects: <home>/.config/bearings/menus.toml
    config_dir = tmp_path / ".config" / "bearings"
    config_dir.mkdir(parents=True)
    (config_dir / "menus.toml").write_bytes(
        b'pin = ["session.fork.from_last_message"]\nhide = ["session.copy_share_link"]\n'
    )

    # Patch Path.home() so the loader resolves to tmp_path.
    fake_home = MagicMock(return_value=tmp_path)
    with patch.object(Path, "home", fake_home):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/api/ui-config")

    cm = resp.json()["context_menus"]
    assert "session.fork.from_last_message" in cm["pin"]
    assert "session.copy_share_link" in cm["hide"]


def test_ui_config_context_menus_malformed_toml(tmp_path: Path) -> None:
    """Malformed menus.toml returns empty config rather than crashing."""
    (tmp_path / ".config" / "bearings").mkdir(parents=True)
    menus_toml = tmp_path / ".config" / "bearings" / "menus.toml"
    menus_toml.write_bytes(b"NOT VALID TOML ]]]\n")

    fake_home = MagicMock(return_value=tmp_path)
    with patch.object(Path, "home", fake_home):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/api/ui-config")

    assert resp.status_code == 200
    cm = resp.json()["context_menus"]
    assert cm["pin"] == []
    assert cm["hide"] == []
