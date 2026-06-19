"""Tests for POST /api/shell/open — fire-and-forget GUI spawn (M-12/R-4)."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from bearings.config.settings import ShellCfg
from bearings.web.app import create_app


@pytest.fixture
def app_client() -> Iterator[TestClient]:
    """Boot the app with the default shell allowlist (includes xdg-open)."""
    app = create_app(shell_cfg=ShellCfg())
    with TestClient(app) as client:
        yield client


@pytest.fixture
def empty_allowlist_client() -> Iterator[TestClient]:
    """Boot the app with an empty allowed_commands (shell unconfigured)."""
    app = create_app(shell_cfg=ShellCfg(allowed_commands=frozenset()))
    with TestClient(app) as client:
        yield client


def test_shell_open_204_on_valid_argv(app_client: TestClient) -> None:
    """Valid allowlisted argv returns 204 immediately (Popen mocked to avoid real spawn)."""
    with patch("bearings.agent.shell.subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        resp = app_client.post("/api/shell/open", json={"argv": ["xdg-open", "/tmp/foo.txt"]})
    assert resp.status_code == 204
    mock_popen.assert_called_once()
    call_args = mock_popen.call_args
    assert call_args.args[0] == ["xdg-open", "/tmp/foo.txt"]
    # Verify fire-and-forget flags
    assert call_args.kwargs.get("start_new_session") is True
    assert "capture_output" not in call_args.kwargs


def test_shell_open_400_when_no_allowlist(empty_allowlist_client: TestClient) -> None:
    """Returns 400 when the allowlist is empty (shell not configured)."""
    resp = empty_allowlist_client.post("/api/shell/open", json={"argv": ["xdg-open", "/tmp"]})
    assert resp.status_code == 400


def test_shell_open_422_when_not_allowlisted(app_client: TestClient) -> None:
    """Returns 422 when argv[0] is not in the allowlist."""
    resp = app_client.post("/api/shell/open", json={"argv": ["rm", "-rf", "/"]})
    assert resp.status_code == 422


def test_shell_open_422_when_argv_empty(app_client: TestClient) -> None:
    """Returns 422 when argv is empty."""
    resp = app_client.post("/api/shell/open", json={"argv": []})
    assert resp.status_code == 422


def test_shell_open_422_when_argv0_has_path_separator(app_client: TestClient) -> None:
    """Returns 422 when argv[0] contains a path separator."""
    resp = app_client.post("/api/shell/open", json={"argv": ["/usr/bin/xdg-open", "/tmp"]})
    assert resp.status_code == 422
