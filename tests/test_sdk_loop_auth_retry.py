# mypy: disable-error-code=explicit-any
"""Regression tests for SDK loop 401-auth-retry logic (item 625).

Simulates a mid-session token rotation by having the first SDK client
raise "Invalid authentication credentials" on ``query()``.  The loop
must detect the auth error, trigger a credential reload, create a fresh
client (new subprocess picks up the rotated bearer), and recover to the
idle-awaiting-user state without marking the session ERROR.

A second test verifies that a second consecutive 401 on the retry does
surface as a terminal error.  The reload mock re-enqueues a prompt so
the second client's ``query()`` actually fires (the first prompt was
consumed by the first attempt).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

import aiosqlite
import pytest
from claude_agent_sdk import AssistantMessage, Message, ResultMessage, TextBlock

from bearings.agent.bearings_mcp import (
    BearingsMcpDeps,
    CloseSessionDeps,
    build_bearings_mcp_server,
)
from bearings.agent.events import ErrorEvent
from bearings.agent.options import compose_session_options
from bearings.agent.routing import RoutingDecision
from bearings.agent.runner import SessionRunner
from bearings.agent.sdk_loop import run_session_loop
from bearings.agent.sdk_loop_errors import TokenExpiredError
from bearings.agent.session import AgentSession, SessionConfig, SessionState
from bearings.config.constants import SESSION_KIND_CHAT
from bearings.db import sessions as sessions_db
from bearings.db.connection import load_schema

# ---------------------------------------------------------------------------
# Shared test infrastructure
# ---------------------------------------------------------------------------

_AUTH_ERROR_MSG = "Invalid authentication credentials"


class _FakeClient:
    """Minimal SDK-client stand-in that records calls and returns scripted responses.

    ``raise_on_query`` — when set, ``query()`` raises a ``RuntimeError``
    with this message instead of succeeding.
    """

    instances: ClassVar[list[_FakeClient]] = []

    def __init__(self, *, options: Any, raise_on_query: str | None = None) -> None:
        self.options = options
        self.raise_on_query: str | None = raise_on_query
        self.queries: list[str] = []
        _FakeClient.instances.append(self)

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def query(self, prompt: str, session_id: str = "default") -> None:
        self.queries.append(prompt)
        if self.raise_on_query:
            raise RuntimeError(self.raise_on_query)

    async def receive_response(self) -> AsyncIterator[Message]:
        # Empty async generator — no messages, no result.
        # ``for _ in ()`` keeps Python treating this as an async generator
        # (a ``yield`` must appear in the body) without producing reachable
        # values.  The loop body is never entered; pragma suppresses coverage.
        for _ in ():  # pragma: no cover
            yield  # type: ignore[misc]


_AUTH_CONTENT_TEXT = "Failed to authenticate. API Error: 401 Invalid authentication credentials"


class _FakeClientWithAuthContent:
    """SDK-client stand-in that surfaces a 401 as AssistantMessage content.

    This is the content-path 401 scenario: the CLI emits an ``assistant``
    message carrying the raw API error text and ``error='authentication_failed'``,
    followed by a ``result`` message with ``is_error=True``.  No Python exception
    is raised — the error is embedded in the message stream.
    """

    instances: ClassVar[list[_FakeClientWithAuthContent]] = []

    def __init__(self, *, options: Any, auth_error: bool = False) -> None:
        self.options = options
        self.auth_error = auth_error
        self.queries: list[str] = []
        _FakeClientWithAuthContent.instances.append(self)

    async def __aenter__(self) -> _FakeClientWithAuthContent:
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def query(self, prompt: str, session_id: str = "default") -> None:
        self.queries.append(prompt)

    async def receive_response(self) -> AsyncIterator[Message]:
        if self.auth_error:
            yield AssistantMessage(
                content=[TextBlock(text=_AUTH_CONTENT_TEXT)],
                model="claude-sonnet",
                message_id="msg_auth_err",
                parent_tool_use_id=None,
                error="authentication_failed",
                usage=None,
                stop_reason=None,
                session_id="ses_t",
                uuid="u-ae",
            )
            yield ResultMessage(
                subtype="error_during_execution",
                duration_ms=100,
                duration_api_ms=80,
                is_error=True,
                num_turns=1,
                session_id="ses_t",
                result=_AUTH_CONTENT_TEXT,
                api_error_status=401,
            )
        else:
            return


def _decision() -> RoutingDecision:
    return RoutingDecision(
        executor_model="sonnet",
        advisor_model=None,
        advisor_max_uses=0,
        effort_level="medium",
        source="default",
        reason="test",
        matched_rule_id=None,
    )


def _options(server: Any) -> Any:
    return compose_session_options(
        decision=_decision(),
        session_instructions=None,
        working_dir="/tmp/wd",
        permission_profile="standard",
        permission_mode_override=None,
        setting_sources=None,
        max_budget_usd=None,
        bearings_mcp_server=server,
    )


def _build_session(conn: aiosqlite.Connection, session_id: str) -> AgentSession:
    config = SessionConfig(
        session_id=session_id,
        working_dir="/tmp/wd",
        decision=_decision(),
        db=conn,
    )
    return AgentSession(config)


@pytest.fixture
async def conn(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(db_path) as connection:
        await load_schema(connection)
        yield connection


@pytest.fixture(autouse=True)
def _reset_clients() -> None:
    _FakeClient.instances = []


def _unused_factory() -> Any:
    async def _never() -> aiosqlite.Connection:  # pragma: no cover
        raise AssertionError("should not be called in unit test")

    return _never


# ---------------------------------------------------------------------------
# Test 1 — 401 on first attempt; second attempt enters idle → loop recovers
# ---------------------------------------------------------------------------


async def test_401_retry_loop_recovers(conn: aiosqlite.Connection) -> None:
    """First client raises 401 on query; after credential reload the second
    client connects cleanly; loop enters idle-awaiting-user (not ERROR).

    This is the canonical token-rotation regression test (item 625).
    The first prompt is consumed by the failing first attempt; the
    second attempt finds an empty queue and enters the idle state.
    """
    session_row = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title="t", working_dir="/tmp/wd", model="sonnet"
    )
    runner = SessionRunner(session_row.id)
    agent = _build_session(conn, session_row.id)
    server = build_bearings_mcp_server(
        BearingsMcpDeps.minimal(
            CloseSessionDeps(session_id=session_row.id, db_factory=_unused_factory())
        )
    )
    # Enqueue one prompt to trigger the first query() call.
    runner.enqueue_prompt(message_id="msg_u1", content="hello after rotation")

    call_count = [0]

    def _factory(*, options: Any) -> _FakeClient:
        call_count[0] += 1
        # First client raises 401; second client succeeds silently.
        if call_count[0] == 1:
            return _FakeClient(options=options, raise_on_query=_AUTH_ERROR_MSG)
        return _FakeClient(options=options, raise_on_query=None)

    reload_calls: list[str] = []

    def _fake_reload() -> None:
        reload_calls.append("reload")

    with patch("bearings.agent.sdk_loop_core._reload_sdk_credentials", _fake_reload):
        task = asyncio.create_task(
            run_session_loop(runner, agent, _options(server), client_factory=_factory)
        )
        # Allow the loop to fail once, reload, create a second client,
        # and enter the idle-awaiting-user state.
        for _ in range(80):
            await asyncio.sleep(0.01)
            if runner.status.is_awaiting_user:
                break
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # The loop must NOT be in ERROR — it recovered after the 401 retry.
    assert agent.state is not SessionState.ERROR, "loop should not be in ERROR after 401 retry"
    # Credential reload was triggered exactly once.
    assert reload_calls == ["reload"], "expected exactly one credential reload"
    # Two client instances were created (one per attempt).
    assert call_count[0] == 2, f"expected 2 client attempts, got {call_count[0]}"
    # No ErrorEvent in the ring buffer.
    error_events = [evt for _, evt in runner._buffer if isinstance(evt, ErrorEvent)]
    assert not error_events, f"unexpected ErrorEvents: {error_events}"


# ---------------------------------------------------------------------------
# Test 2 — 401 on both attempts → terminal error
# ---------------------------------------------------------------------------


async def test_401_retry_twice_surfaces_terminal_error(conn: aiosqlite.Connection) -> None:
    """When both the first attempt AND the retry raise 401, the loop
    transitions to ERROR and emits a fatal ErrorEvent.

    The reload mock re-enqueues a prompt so the second client's
    ``query()`` actually fires (the first prompt was consumed by the
    first failing attempt).
    """
    session_row = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title="t2", working_dir="/tmp/wd", model="sonnet"
    )
    runner = SessionRunner(session_row.id)
    agent = _build_session(conn, session_row.id)
    server = build_bearings_mcp_server(
        BearingsMcpDeps.minimal(
            CloseSessionDeps(session_id=session_row.id, db_factory=_unused_factory())
        )
    )
    # First prompt — consumed by first attempt which 401s.
    runner.enqueue_prompt(message_id="msg_u2", content="always 401")

    def _always_401(*, options: Any) -> _FakeClient:
        return _FakeClient(options=options, raise_on_query=_AUTH_ERROR_MSG)

    def _reload_and_requeue() -> None:
        # Re-enqueue so the second client's query() actually fires.
        runner.enqueue_prompt(message_id="msg_retry", content="retry — also 401")

    with patch("bearings.agent.sdk_loop_core._reload_sdk_credentials", _reload_and_requeue):
        await run_session_loop(runner, agent, _options(server), client_factory=_always_401)

    assert agent.state is SessionState.ERROR
    error_events = [evt for _, evt in runner._buffer if isinstance(evt, ErrorEvent)]
    assert len(error_events) == 1
    assert error_events[0].fatal is True
    assert _AUTH_ERROR_MSG in error_events[0].message


# ---------------------------------------------------------------------------
# Test 3 — expired token: no retry subprocess spawned, clear actionable error
# ---------------------------------------------------------------------------


async def test_401_expired_token_no_retry_subprocess(conn: aiosqlite.Connection) -> None:
    """When _reload_sdk_credentials raises TokenExpiredError (token past its
    expiry date), the loop must NOT spawn a second subprocess.  It transitions
    to ERROR immediately with an actionable re-authentication message.

    This covers long-idle sessions (14+ hours) where the token is fully
    expired and re-authentication is required before any retry can succeed.
    """
    session_row = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title="t3", working_dir="/tmp/wd", model="sonnet"
    )
    runner = SessionRunner(session_row.id)
    agent = _build_session(conn, session_row.id)
    server = build_bearings_mcp_server(
        BearingsMcpDeps.minimal(
            CloseSessionDeps(session_id=session_row.id, db_factory=_unused_factory())
        )
    )
    runner.enqueue_prompt(message_id="msg_u3", content="long-idle session, token expired")

    call_count = [0]

    def _first_401_factory(*, options: Any) -> _FakeClient:
        call_count[0] += 1
        return _FakeClient(options=options, raise_on_query=_AUTH_ERROR_MSG)

    def _raise_token_expired() -> None:
        raise TokenExpiredError(
            "OAuth token expired at 2026-01-01T00:00:00+00:00. "
            "Re-authenticate by running 'claude' in a terminal."
        )

    with patch("bearings.agent.sdk_loop_core._reload_sdk_credentials", _raise_token_expired):
        await run_session_loop(runner, agent, _options(server), client_factory=_first_401_factory)

    # Session must be in ERROR state.
    assert agent.state is SessionState.ERROR
    # Exactly ONE client created — no retry subprocess when token is expired.
    assert call_count[0] == 1, f"expected 1 client (no retry), got {call_count[0]}"
    # The ErrorEvent message must carry the actionable re-auth hint.
    error_events = [evt for _, evt in runner._buffer if isinstance(evt, ErrorEvent)]
    assert len(error_events) == 1
    assert error_events[0].fatal is True
    assert "Re-authenticate" in error_events[0].message


# ---------------------------------------------------------------------------
# Test 4 — 401 as AssistantMessage content (not exception): retry fires
# ---------------------------------------------------------------------------


async def test_401_content_path_triggers_retry(conn: aiosqlite.Connection) -> None:
    """Auth failure surfaced as AssistantMessage content triggers credential-reload.

    The CLI can emit a 401 as an assistant message body (with
    ``error='authentication_failed'``) rather than as a Python exception.
    The fix in ``_do_run_one_turn`` must detect this and raise so the same
    credential-reload retry path fires — preventing the error text from
    being persisted as a regular chat message.
    """
    session_row = await sessions_db.create(
        conn, kind=SESSION_KIND_CHAT, title="t4", working_dir="/tmp/wd", model="sonnet"
    )
    runner = SessionRunner(session_row.id)
    agent = _build_session(conn, session_row.id)
    server = build_bearings_mcp_server(
        BearingsMcpDeps.minimal(
            CloseSessionDeps(session_id=session_row.id, db_factory=_unused_factory())
        )
    )
    runner.enqueue_prompt(message_id="msg_u4", content="content-path 401")

    call_count = [0]

    def _factory(*, options: Any) -> _FakeClientWithAuthContent:
        call_count[0] += 1
        # First client returns auth error as content; second succeeds silently.
        return _FakeClientWithAuthContent(options=options, auth_error=(call_count[0] == 1))

    reload_calls: list[str] = []

    def _fake_reload() -> None:
        reload_calls.append("reload")

    with patch("bearings.agent.sdk_loop_core._reload_sdk_credentials", _fake_reload):
        task = asyncio.create_task(
            run_session_loop(runner, agent, _options(server), client_factory=_factory)
        )
        for _ in range(80):
            await asyncio.sleep(0.01)
            if runner.status.is_awaiting_user:
                break
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # Loop must NOT be in ERROR — it recovered via the content-path retry.
    assert agent.state is not SessionState.ERROR, (
        "loop should not be in ERROR after content-path 401 retry"
    )
    # Credential reload was triggered exactly once.
    assert reload_calls == ["reload"], "expected exactly one credential reload"
    # Two client instances were created.
    assert call_count[0] == 2, f"expected 2 client attempts, got {call_count[0]}"
    # No ErrorEvent — the error must not have been emitted as a fatal event.
    error_events = [evt for _, evt in runner._buffer if isinstance(evt, ErrorEvent) and evt.fatal]
    assert not error_events, f"unexpected fatal ErrorEvents: {error_events}"
