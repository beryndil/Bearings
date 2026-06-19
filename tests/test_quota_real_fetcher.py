# mypy: disable-error-code=explicit-any
"""Tests for bearings.agent.quota.build_real_fetcher.

All tests mock the subprocess call — no real claude binary is invoked.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from bearings.agent.quota import QuotaSnapshot, build_real_fetcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_usage_result(
    session_pct: int | None = 27,
    weekly_all_pct: int | None = 7,
    sonnet_pct: int | None = 8,
) -> str:
    """Build a /usage result string matching the real CLI output format."""
    lines = ["You are currently using your subscription to power your Claude Code usage"]
    if session_pct is not None:
        lines.append(f"Current session: {session_pct}% used · resets Jun 19, 9pm (America/Chicago)")
    if weekly_all_pct is not None:
        lines.append(
            f"Current week (all models): {weekly_all_pct}% used"
            " · resets Jun 23, 7pm (America/Chicago)"
        )
    if sonnet_pct is not None:
        lines.append(
            f"Current week (Sonnet only): {sonnet_pct}% used"
            " · resets Jun 23, 6:59pm (America/Chicago)"
        )
    return "\n".join(lines)


def _make_cli_json_output(result: str) -> bytes:
    """Encode a minimal claude CLI JSON output with the given result text."""
    payload = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": result,
        "session_id": "fake-session",
        "duration_ms": 500,
        "duration_api_ms": 0,
        "num_turns": 0,
        "stop_reason": None,
        "total_cost_usd": 0,
        "usage": {},
        "modelUsage": {},
    }
    return json.dumps(payload).encode("utf-8")


class _FakeProcess:
    """Minimal asyncio.subprocess.Process stub."""

    def __init__(self, stdout: bytes, returncode: int = 0) -> None:
        self._stdout = stdout
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, b""

    def kill(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_build_real_fetcher_returns_callable() -> None:
    """Factory produces a coroutine function (no I/O at construction time)."""
    import inspect

    fn = build_real_fetcher()
    assert inspect.iscoroutinefunction(fn)


@pytest.mark.asyncio
async def test_build_real_fetcher_parses_session_and_sonnet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parses overall (session) and sonnet percentages from CLI output."""
    result_text = _make_usage_result(session_pct=45, sonnet_pct=12)
    output = _make_cli_json_output(result_text)

    async def _fake_exec(*_args: Any, **_kwargs: Any) -> _FakeProcess:
        return _FakeProcess(stdout=output)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    fn = build_real_fetcher()
    snapshot: QuotaSnapshot = await fn()
    assert isinstance(snapshot, QuotaSnapshot)
    assert snapshot.overall_used_pct == pytest.approx(0.45)
    assert snapshot.sonnet_used_pct == pytest.approx(0.12)


@pytest.mark.asyncio
async def test_build_real_fetcher_returns_none_when_lines_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the expected lines are missing, both pcts are None (fail-open)."""
    output = _make_cli_json_output("No usage info available.")

    async def _fake_exec(*_args: Any, **_kwargs: Any) -> _FakeProcess:
        return _FakeProcess(stdout=output)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    fn = build_real_fetcher()
    snapshot: QuotaSnapshot = await fn()
    assert snapshot.overall_used_pct is None
    assert snapshot.sonnet_used_pct is None


@pytest.mark.asyncio
async def test_build_real_fetcher_raw_payload_has_source_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """raw_payload JSON includes source='claude_usage' for forward compat."""
    result_text = _make_usage_result(session_pct=10, sonnet_pct=5)
    output = _make_cli_json_output(result_text)

    async def _fake_exec(*_args: Any, **_kwargs: Any) -> _FakeProcess:
        return _FakeProcess(stdout=output)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    fn = build_real_fetcher()
    snapshot: QuotaSnapshot = await fn()
    raw = json.loads(snapshot.raw_payload)
    assert raw.get("source") == "claude_usage"
    assert "text" in raw


@pytest.mark.asyncio
async def test_build_real_fetcher_raises_connection_error_on_file_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FileNotFoundError from subprocess → ConnectionError (poller catches it)."""

    async def _fake_exec(*_args: Any, **_kwargs: Any) -> _FakeProcess:
        raise FileNotFoundError("claude not found")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    fn = build_real_fetcher()
    with pytest.raises(ConnectionError, match="not found"):
        await fn()


@pytest.mark.asyncio
async def test_build_real_fetcher_raises_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """asyncio.TimeoutError from wait_for → TimeoutError (poller catches it)."""

    class _SlowProcess(_FakeProcess):
        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(9999)  # never finishes
            return b"", b""

    async def _fake_exec(*_args: Any, **_kwargs: Any) -> _FakeProcess:
        return _SlowProcess(stdout=b"")

    async def _fake_wait_for(coro: object, *_args: object, **_kwargs: object) -> None:
        if hasattr(coro, "close"):
            coro.close()  # prevent "coroutine was never awaited" warning
        raise TimeoutError("timed out")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr(asyncio, "wait_for", _fake_wait_for)

    fn = build_real_fetcher()
    with pytest.raises(TimeoutError, match="timed out"):
        await fn()


@pytest.mark.asyncio
async def test_build_real_fetcher_raises_runtime_error_on_bad_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid JSON from the CLI → RuntimeError (poller catches it)."""

    async def _fake_exec(*_args: Any, **_kwargs: Any) -> _FakeProcess:
        return _FakeProcess(stdout=b"not json at all")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    fn = build_real_fetcher()
    with pytest.raises(RuntimeError, match="JSON decode error"):
        await fn()


@pytest.mark.asyncio
async def test_build_real_fetcher_handles_80_percent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exactly 80% overall triggers the quota guard — ensure correct parse."""
    result_text = _make_usage_result(session_pct=80, sonnet_pct=80)
    output = _make_cli_json_output(result_text)

    async def _fake_exec(*_args: Any, **_kwargs: Any) -> _FakeProcess:
        return _FakeProcess(stdout=output)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    fn = build_real_fetcher()
    snapshot: QuotaSnapshot = await fn()
    assert snapshot.overall_used_pct == pytest.approx(0.80)
    assert snapshot.sonnet_used_pct == pytest.approx(0.80)


@pytest.mark.asyncio
async def test_build_real_fetcher_captured_at_is_recent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """captured_at is a recent unix timestamp (within 10 seconds of now)."""
    import time

    result_text = _make_usage_result(session_pct=10, sonnet_pct=5)
    output = _make_cli_json_output(result_text)

    async def _fake_exec(*_args: Any, **_kwargs: Any) -> _FakeProcess:
        return _FakeProcess(stdout=output)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    before = int(time.time())
    fn = build_real_fetcher()
    snapshot: QuotaSnapshot = await fn()
    after = int(time.time())
    assert before <= snapshot.captured_at <= after + 1
