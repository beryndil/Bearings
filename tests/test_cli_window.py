"""Tests for the ``bearings window`` subcommand.

Acceptance-criteria coverage:

* AC-win-1  Window opens via Firefox when firefox is on PATH.
* AC-win-2  Window opens via Chromium when firefox absent but chromium present.
* AC-win-3  --browser overrides autodetection.
* AC-win-4  --plain mode uses bare [browser, url] argv.
* AC-win-5  --profile mode uses specified profile directory for Firefox.
* AC-win-6  --plain and --profile together → stderr + exit 2.
* AC-win-7  No browser found → stderr listing candidates + exit 1.
* AC-win-8  Success message printed to stderr (not stdout).
* AC-win-9  Stdout is empty on success.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bearings.cli.app import main
from bearings.cli.window import (
    _build_browser_cmd,
    _find_browser,
)
from bearings.config.constants import (
    CLI_EXIT_OK,
    CLI_EXIT_OPERATION_FAILURE,
    CLI_EXIT_USAGE_ERROR,
    DEFAULT_WINDOW_FIREFOX_PROFILE_DIR,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_popen(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch subprocess.Popen so no real browser is launched."""
    mock = MagicMock()
    monkeypatch.setattr("bearings.cli.window.subprocess.Popen", mock)
    return mock


def _which_returns(monkeypatch: pytest.MonkeyPatch, which_map: dict[str, str | None]) -> None:
    """Patch shutil.which to return predetermined paths."""

    def fake_which(name: str) -> str | None:
        return which_map.get(name)

    monkeypatch.setattr("bearings.cli.window.shutil.which", fake_which)


# ---------------------------------------------------------------------------
# AC-win-1  Firefox autodetect
# ---------------------------------------------------------------------------


def test_window_opens_via_firefox(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _which_returns(monkeypatch, {"firefox": "/usr/bin/firefox"})
    mock_popen = _mock_popen(monkeypatch)

    rc = main(["window"])
    assert rc == CLI_EXIT_OK
    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert cmd[0] == "/usr/bin/firefox"
    assert "--new-window" in cmd
    assert any("firefox-profile" in arg for arg in cmd)


def test_window_firefox_stderr_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _which_returns(monkeypatch, {"firefox": "/usr/bin/firefox"})
    _mock_popen(monkeypatch)

    main(["window"])
    out, err = capsys.readouterr()
    assert out == ""  # stdout empty
    assert "bearings window: opened" in err
    assert "/usr/bin/firefox" in err


# ---------------------------------------------------------------------------
# AC-win-2  Chromium fallback
# ---------------------------------------------------------------------------


def test_window_falls_back_to_chromium(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _which_returns(monkeypatch, {"chromium": "/usr/bin/chromium"})
    mock_popen = _mock_popen(monkeypatch)

    rc = main(["window"])
    assert rc == CLI_EXIT_OK
    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert cmd[0] == "/usr/bin/chromium"
    # Chromium gets --app=URL, not --new-window
    assert any(arg.startswith("--app=") for arg in cmd)
    assert "--new-window" not in cmd


# ---------------------------------------------------------------------------
# AC-win-3  --browser override
# ---------------------------------------------------------------------------


def test_window_browser_override(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # which() returns a path for the override name
    monkeypatch.setattr(
        "bearings.cli.window.shutil.which",
        lambda name: f"/custom/{name}" if name == "my-browser" else None,
    )
    mock_popen = _mock_popen(monkeypatch)

    rc = main(["window", "--browser", "my-browser"])
    assert rc == CLI_EXIT_OK
    cmd = mock_popen.call_args[0][0]
    assert "/custom/my-browser" in cmd[0]


def test_window_browser_override_absolute_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # If which() returns None, the verbatim path is used.
    monkeypatch.setattr("bearings.cli.window.shutil.which", lambda name: None)
    mock_popen = _mock_popen(monkeypatch)

    rc = main(["window", "--browser", "/opt/browser/mybrowser"])
    assert rc == CLI_EXIT_OK
    cmd = mock_popen.call_args[0][0]
    assert cmd[0] == "/opt/browser/mybrowser"


# ---------------------------------------------------------------------------
# AC-win-4  --plain mode
# ---------------------------------------------------------------------------


def test_window_plain_mode_omits_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _which_returns(monkeypatch, {"firefox": "/usr/bin/firefox"})
    mock_popen = _mock_popen(monkeypatch)

    rc = main(["window", "--plain"])
    assert rc == CLI_EXIT_OK
    cmd = mock_popen.call_args[0][0]
    assert "--profile" not in cmd
    assert "--new-window" not in cmd
    # Bare [browser, url]
    assert len(cmd) == 2


def test_window_plain_mode_chromium_no_app_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _which_returns(monkeypatch, {"chromium": "/usr/bin/chromium"})
    mock_popen = _mock_popen(monkeypatch)

    rc = main(["window", "--plain"])
    assert rc == CLI_EXIT_OK
    cmd = mock_popen.call_args[0][0]
    assert not any(arg.startswith("--app=") for arg in cmd)
    assert len(cmd) == 2


# ---------------------------------------------------------------------------
# AC-win-5  --profile mode
# ---------------------------------------------------------------------------


def test_window_profile_mode_firefox(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _which_returns(monkeypatch, {"firefox": "/usr/bin/firefox"})
    mock_popen = _mock_popen(monkeypatch)

    rc = main(["window", "--profile", str(tmp_path)])
    assert rc == CLI_EXIT_OK
    cmd = mock_popen.call_args[0][0]
    assert "--profile" in cmd
    idx = cmd.index("--profile")
    assert cmd[idx + 1] == str(tmp_path)


# ---------------------------------------------------------------------------
# AC-win-6  --plain + --profile mutual exclusion
# ---------------------------------------------------------------------------


def test_window_plain_and_profile_together_exits_2(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _which_returns(monkeypatch, {"firefox": "/usr/bin/firefox"})
    _mock_popen(monkeypatch)

    rc = main(["window", "--plain", "--profile", str(tmp_path)])
    assert rc == CLI_EXIT_USAGE_ERROR
    err = capsys.readouterr().err
    assert "--plain and --profile are mutually exclusive" in err


# ---------------------------------------------------------------------------
# AC-win-7  No browser found
# ---------------------------------------------------------------------------


def test_window_no_browser_exits_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _which_returns(monkeypatch, {})
    _mock_popen(monkeypatch)

    rc = main(["window"])
    assert rc == CLI_EXIT_OPERATION_FAILURE
    err = capsys.readouterr().err
    assert "bearings window: no browser found" in err
    # Must list some candidates
    assert "firefox" in err


def test_window_no_browser_offers_paste_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _which_returns(monkeypatch, {})
    _mock_popen(monkeypatch)

    main(["window", "--host", "127.0.0.1", "--port", "8787"])
    err = capsys.readouterr().err
    assert "http://127.0.0.1:8787/" in err
    assert "bearings window --browser" in err


# ---------------------------------------------------------------------------
# AC-win-8 / AC-win-9  stderr/stdout discipline
# ---------------------------------------------------------------------------


def test_window_stdout_empty_on_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _which_returns(monkeypatch, {"firefox": "/usr/bin/firefox"})
    _mock_popen(monkeypatch)

    main(["window"])
    out = capsys.readouterr().out
    assert out == ""


# ---------------------------------------------------------------------------
# Unit tests for internal helpers
# ---------------------------------------------------------------------------


def test_find_browser_returns_first_firefox_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "bearings.cli.window.shutil.which",
        lambda n: f"/usr/bin/{n}" if n == "firefox" else None,
    )
    path, is_ff = _find_browser(None)
    assert path == "/usr/bin/firefox"
    assert is_ff is True


def test_find_browser_skips_to_chromium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "bearings.cli.window.shutil.which",
        lambda n: "/usr/bin/chromium" if n == "chromium" else None,
    )
    path, is_ff = _find_browser(None)
    assert path == "/usr/bin/chromium"
    assert is_ff is False


def test_find_browser_none_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("bearings.cli.window.shutil.which", lambda n: None)
    path, is_ff = _find_browser(None)
    assert path is None
    assert is_ff is False


def test_build_browser_cmd_plain() -> None:
    cmd = _build_browser_cmd("/usr/bin/firefox", "http://localhost/", True, True, None)
    assert cmd == ["/usr/bin/firefox", "http://localhost/"]


def test_build_browser_cmd_firefox_default_profile() -> None:
    cmd = _build_browser_cmd("/usr/bin/firefox", "http://localhost/", True, False, None)
    assert cmd[0] == "/usr/bin/firefox"
    assert "--new-window" in cmd
    assert "--profile" in cmd
    assert str(DEFAULT_WINDOW_FIREFOX_PROFILE_DIR) in cmd


def test_build_browser_cmd_firefox_custom_profile(tmp_path: Path) -> None:
    cmd = _build_browser_cmd("/usr/bin/firefox", "http://localhost/", True, False, tmp_path)
    assert "--profile" in cmd
    idx = cmd.index("--profile")
    assert cmd[idx + 1] == str(tmp_path)


def test_build_browser_cmd_chromium() -> None:
    cmd = _build_browser_cmd("/usr/bin/chromium", "http://localhost/", False, False, None)
    assert cmd[0] == "/usr/bin/chromium"
    assert "--app=http://localhost/" in cmd
    assert "--profile" not in cmd
