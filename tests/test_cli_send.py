"""Tests for the ``bearings send`` subcommand.

Acceptance-criteria coverage:

* AC-send-1  --session is required; omitting it exits 2.
* AC-send-2  message_complete event → exit 0 and frame printed (json mode).
* AC-send-3  error event → exit 1.
* AC-send-4  --format pretty renders tokens inline, rule at turn end.
* AC-send-5  Connection failure → stderr message + exit 1.
* AC-send-6  Prompt is POSTed with correct JSON body.
* AC-send-7  --token sets Authorization header.
* AC-send-8  Heartbeat frames are silently ignored.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from bearings.cli.app import main
from bearings.cli.send import (
    _print_event,
    _run_send,
)
from bearings.config.constants import (
    CLI_EXIT_OK,
    CLI_EXIT_OPERATION_FAILURE,
    CLI_EXIT_USAGE_ERROR,
    SEND_PRETTY_RULE_WIDTH,
)

# ---------------------------------------------------------------------------
# Async WebSocket mock infrastructure
# ---------------------------------------------------------------------------


class _MockWs:
    """Async iterable yielding pre-canned WebSocket text frames."""

    def __init__(self, frames: list[str]) -> None:
        self._frames = frames

    def __aiter__(self) -> _MockWs:
        self._iter = iter(self._frames)
        return self

    async def __anext__(self) -> str:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _ws_frame(event: dict[str, object], seq: int = 1) -> str:
    """Build a ``kind=event`` WebSocket frame string."""
    return json.dumps({"kind": "event", "seq": seq, "event": event})


def _heartbeat_frame() -> str:
    return json.dumps({"kind": "heartbeat", "ts": 0.0})


def _make_ws_connect(frames: list[str]) -> object:
    """Return a mock that can be used as ``async with ws_connect(url) as ws``."""

    class _MockConnect:
        def __call__(self, url: str) -> _MockConnect:
            return self

        async def __aenter__(self) -> _MockWs:
            return _MockWs(frames)

        async def __aexit__(self, *args: object) -> None:
            pass

    return _MockConnect()


def _noop_post(url: str, message: str, token: str | None) -> None:
    """No-op stub for the HTTP POST helper."""


# ---------------------------------------------------------------------------
# AC-send-1  --session required
# ---------------------------------------------------------------------------


def test_send_requires_session_id(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["send", "hello"])
    assert rc == CLI_EXIT_USAGE_ERROR


# ---------------------------------------------------------------------------
# AC-send-2  message_complete → exit 0, frame in json output
# ---------------------------------------------------------------------------


def test_send_json_exit_0_on_message_complete(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frames = [
        _ws_frame({"type": "token", "text": "hello"}),
        _ws_frame({"type": "message_complete"}),
    ]
    monkeypatch.setattr("bearings.cli.send._http_post_prompt", _noop_post)
    monkeypatch.setattr("websockets.asyncio.client.connect", _make_ws_connect(frames))

    rc = asyncio.run(
        _run_send(
            session_id="ses_abc123",
            host="127.0.0.1",
            port=8787,
            token=None,
            message="hello",
            format_="json",
        )
    )
    assert rc == CLI_EXIT_OK
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln]
    # At least two events printed: token + message_complete
    assert len(lines) >= 2
    parsed_last = json.loads(lines[-1])
    assert parsed_last.get("type") == "message_complete"


def test_send_json_token_events_printed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frames = [
        _ws_frame({"type": "token", "text": "hello "}),
        _ws_frame({"type": "token", "text": "world"}),
        _ws_frame({"type": "message_complete"}),
    ]
    monkeypatch.setattr("bearings.cli.send._http_post_prompt", _noop_post)
    monkeypatch.setattr("websockets.asyncio.client.connect", _make_ws_connect(frames))

    asyncio.run(
        _run_send(
            session_id="ses_abc",
            host="127.0.0.1",
            port=8787,
            token=None,
            message="test",
            format_="json",
        )
    )
    out = capsys.readouterr().out
    # Three lines: two tokens + message_complete
    lines = [ln for ln in out.splitlines() if ln]
    assert len(lines) == 3
    assert json.loads(lines[0])["type"] == "token"
    assert json.loads(lines[0])["text"] == "hello "


# ---------------------------------------------------------------------------
# AC-send-3  error event → exit 1
# ---------------------------------------------------------------------------


def test_send_exits_1_on_error_event(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frames = [
        _ws_frame({"type": "error", "message": "something failed"}),
    ]
    monkeypatch.setattr("bearings.cli.send._http_post_prompt", _noop_post)
    monkeypatch.setattr("websockets.asyncio.client.connect", _make_ws_connect(frames))

    rc = asyncio.run(
        _run_send(
            session_id="ses_abc",
            host="127.0.0.1",
            port=8787,
            token=None,
            message="test",
            format_="json",
        )
    )
    assert rc == CLI_EXIT_OPERATION_FAILURE


# ---------------------------------------------------------------------------
# AC-send-4  --format pretty renders tokens inline, rule at turn end
# ---------------------------------------------------------------------------


def test_send_pretty_tokens_inline(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frames = [
        _ws_frame({"type": "token", "text": "Hello"}),
        _ws_frame({"type": "token", "text": " world"}),
        _ws_frame({"type": "message_complete"}),
    ]
    monkeypatch.setattr("bearings.cli.send._http_post_prompt", _noop_post)
    monkeypatch.setattr("websockets.asyncio.client.connect", _make_ws_connect(frames))

    asyncio.run(
        _run_send(
            session_id="ses_abc",
            host="127.0.0.1",
            port=8787,
            token=None,
            message="test",
            format_="pretty",
        )
    )
    out = capsys.readouterr().out
    # Tokens appear inline (no JSON wrapping)
    assert "Hello" in out
    assert " world" in out
    # Horizontal rule appears after message_complete
    assert "─" * SEND_PRETTY_RULE_WIDTH in out


def test_send_pretty_tool_start_renders(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frames = [
        _ws_frame({"type": "tool_start", "name": "Bash", "input": "ls /"}),
        _ws_frame({"type": "message_complete"}),
    ]
    monkeypatch.setattr("bearings.cli.send._http_post_prompt", _noop_post)
    monkeypatch.setattr("websockets.asyncio.client.connect", _make_ws_connect(frames))

    asyncio.run(
        _run_send(
            session_id="ses_abc",
            host="127.0.0.1",
            port=8787,
            token=None,
            message="test",
            format_="pretty",
        )
    )
    out = capsys.readouterr().out
    assert "↳ tool Bash" in out


# ---------------------------------------------------------------------------
# AC-send-5  Connection failure
# ---------------------------------------------------------------------------


def test_send_connection_refused_exits_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _FailConnect:
        def __call__(self, url: str) -> _FailConnect:
            return self

        async def __aenter__(self) -> None:
            raise ConnectionRefusedError("refused")

        async def __aexit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr("websockets.asyncio.client.connect", _FailConnect())

    rc = asyncio.run(
        _run_send(
            session_id="ses_abc",
            host="127.0.0.1",
            port=8787,
            token=None,
            message="test",
            format_="json",
        )
    )
    assert rc == CLI_EXIT_OPERATION_FAILURE
    err = capsys.readouterr().err
    assert "bearings send: cannot connect" in err


# ---------------------------------------------------------------------------
# AC-send-6  Prompt POSTed with correct JSON body
# ---------------------------------------------------------------------------


def test_send_posts_message_as_json_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [_ws_frame({"type": "message_complete"})]
    posted: list[dict[str, object]] = []

    def _capture_post(url: str, message: str, token: str | None) -> None:
        posted.append({"url": url, "message": message, "token": token})

    monkeypatch.setattr("bearings.cli.send._http_post_prompt", _capture_post)
    monkeypatch.setattr("websockets.asyncio.client.connect", _make_ws_connect(frames))

    asyncio.run(
        _run_send(
            session_id="ses_xyz",
            host="127.0.0.1",
            port=8787,
            token=None,
            message="my prompt",
            format_="json",
        )
    )
    assert len(posted) == 1
    assert posted[0]["message"] == "my prompt"
    assert "ses_xyz" in str(posted[0]["url"])


# ---------------------------------------------------------------------------
# AC-send-7  --token sets Authorization header
# ---------------------------------------------------------------------------


def test_send_token_forwarded_to_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [_ws_frame({"type": "message_complete"})]
    posted: list[dict[str, object]] = []

    def _capture_post(url: str, message: str, token: str | None) -> None:
        posted.append({"token": token})

    monkeypatch.setattr("bearings.cli.send._http_post_prompt", _capture_post)
    monkeypatch.setattr("websockets.asyncio.client.connect", _make_ws_connect(frames))

    asyncio.run(
        _run_send(
            session_id="ses_abc",
            host="127.0.0.1",
            port=8787,
            token="my-secret-token",
            message="test",
            format_="json",
        )
    )
    assert posted[0]["token"] == "my-secret-token"


# ---------------------------------------------------------------------------
# AC-send-8  Heartbeat frames silently ignored
# ---------------------------------------------------------------------------


def test_send_heartbeat_frames_ignored(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frames = [
        _heartbeat_frame(),
        _heartbeat_frame(),
        _ws_frame({"type": "message_complete"}),
    ]
    monkeypatch.setattr("bearings.cli.send._http_post_prompt", _noop_post)
    monkeypatch.setattr("websockets.asyncio.client.connect", _make_ws_connect(frames))

    rc = asyncio.run(
        _run_send(
            session_id="ses_abc",
            host="127.0.0.1",
            port=8787,
            token=None,
            message="test",
            format_="json",
        )
    )
    assert rc == CLI_EXIT_OK
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln]
    # Only the message_complete event should be in stdout (heartbeats silently dropped)
    assert len(lines) == 1
    assert json.loads(lines[0])["type"] == "message_complete"


# ---------------------------------------------------------------------------
# Unit tests for _print_event
# ---------------------------------------------------------------------------


def test_print_event_json_mode(capsys: pytest.CaptureFixture[str]) -> None:
    _print_event({"type": "token", "text": "hi"}, "json")
    out = capsys.readouterr().out
    assert json.loads(out.strip())["text"] == "hi"


def test_print_event_pretty_token_no_newline(capsys: pytest.CaptureFixture[str]) -> None:
    _print_event({"type": "token", "text": "abc"}, "pretty")
    out = capsys.readouterr().out
    # Token is written inline without a trailing newline
    assert "abc" in out
