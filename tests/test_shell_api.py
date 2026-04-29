"""Integration tests for ``bearings.web.routes.shell`` (item 1.10).

Exercises argv allowlist enforcement, happy-path ``echo``, timeout
mapping to 504, path-separator rejection, and empty-argv 422.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import pytest
from fastapi.testclient import TestClient

from bearings.config.settings import ShellCfg
from bearings.web.app import create_app

_HEARTBEAT_S: Final[float] = 5.0


@pytest.fixture
def app_client() -> Iterator[TestClient]:
    """Boot the app with the default shell allowlist (echo/true/xdg-open)."""
    app = create_app(heartbeat_interval_s=_HEARTBEAT_S, shell_cfg=ShellCfg())
    with TestClient(app) as client:
        yield client


def test_post_exec_runs_whitelisted_echo(app_client: TestClient) -> None:
    response = app_client.post("/api/shell/exec", json={"argv": ["echo", "hi"]})
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] == 0
    assert body["reason"] == "exited"
    assert body["stdout"].strip() == "hi"
    assert body["stderr"] == ""


def test_post_exec_422_when_argv_not_allowlisted(
    app_client: TestClient,
) -> None:
    response = app_client.post(
        "/api/shell/exec",
        json={"argv": ["rm", "-rf", "/"]},
    )
    assert response.status_code == 422


def test_post_exec_422_when_argv_empty(app_client: TestClient) -> None:
    response = app_client.post("/api/shell/exec", json={"argv": []})
    # Pydantic's min_length=1 fires before our validator.
    assert response.status_code == 422


def test_post_exec_422_when_argv0_has_path_separator(
    app_client: TestClient,
) -> None:
    response = app_client.post(
        "/api/shell/exec",
        json={"argv": ["/bin/echo", "hi"]},
    )
    assert response.status_code == 422


def test_post_exec_504_on_timeout() -> None:
    """A short timeout against ``true`` won't trip; build a fixture
    with a custom allowlist + tiny timeout against ``sleep``."""
    cfg = ShellCfg(allowed_commands=frozenset({"sleep"}), timeout_s=0.1)
    app = create_app(heartbeat_interval_s=_HEARTBEAT_S, shell_cfg=cfg)
    with TestClient(app) as client:
        response = client.post("/api/shell/exec", json={"argv": ["sleep", "5"]})
        assert response.status_code == 504


def test_post_exec_returns_spawn_error_when_binary_missing() -> None:
    """A bare command name that isn't on PATH returns 200 +
    ``reason=spawn_error``; the API is up, the spawn failed."""
    cfg = ShellCfg(allowed_commands=frozenset({"definitely-not-a-binary-xyz"}))
    app = create_app(heartbeat_interval_s=_HEARTBEAT_S, shell_cfg=cfg)
    with TestClient(app) as client:
        response = client.post(
            "/api/shell/exec",
            json={"argv": ["definitely-not-a-binary-xyz"]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["reason"] == "spawn_error"
        assert body["exit_code"] == -1
