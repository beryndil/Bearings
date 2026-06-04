"""Tests for GET /api/ui-config."""

from __future__ import annotations

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
