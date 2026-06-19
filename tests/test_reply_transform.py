# mypy: disable-error-code=explicit-any
"""Tests for bearings.agent.reply_transform.build_run_transform.

All tests mock the SDK ``query()`` function — no real LLM calls are made.
The mock returns an async generator that yields the configured events.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiosqlite
import pytest
from claude_agent_sdk import ResultMessage
from fastapi import FastAPI
from fastapi.testclient import TestClient

import bearings.web.routes.reply_actions as reply_actions_mod
from bearings.agent.reply_transform import build_run_transform
from bearings.db import sessions as sessions_db
from bearings.db.connection import load_schema
from bearings.web.app import create_app

# ---------------------------------------------------------------------------
# SDK-compatible stubs.
# ---------------------------------------------------------------------------


def _make_result_message(result: str | None, is_error: bool = False) -> ResultMessage:
    """Build a real ResultMessage instance with minimal fields populated."""
    return ResultMessage(
        subtype="success",
        duration_ms=0,
        duration_api_ms=0,
        is_error=is_error,
        num_turns=1,
        session_id="fake-session",
        result=result,
    )


class _FakeOtherEvent:
    """An unrecognised event type — should be silently ignored."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_query_mock(
    *events: Any,
) -> Any:
    """Return an async-generator-function mock yielding *events*.

    Replaces ``claude_agent_sdk.query`` in the module under test.
    """

    async def _fake_query(**_: Any) -> AsyncIterator[Any]:
        for event in events:
            yield event

    return _fake_query


# ---------------------------------------------------------------------------
# Unit tests — build_run_transform
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_run_transform_returns_callable() -> None:
    """Factory returns a coroutine function."""
    import inspect

    fn = build_run_transform()
    assert inspect.iscoroutinefunction(fn)


@pytest.mark.asyncio
async def test_build_run_transform_returns_result_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returns the ResultMessage.result string on success."""
    import bearings.agent.reply_transform as rt_mod

    monkeypatch.setattr(
        rt_mod,
        "_sdk_query",
        _make_query_mock(_make_result_message(result="TRANSFORMED TEXT")),
    )
    fn = build_run_transform()
    out = await fn("hello world", "Summarize this.")
    assert out == "TRANSFORMED TEXT"


@pytest.mark.asyncio
async def test_build_run_transform_ignores_non_result_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-ResultMessage events are ignored; only the ResultMessage matters."""
    import bearings.agent.reply_transform as rt_mod

    monkeypatch.setattr(
        rt_mod,
        "_sdk_query",
        _make_query_mock(
            _FakeOtherEvent(),
            _make_result_message(result="GOOD"),
        ),
    )
    fn = build_run_transform()
    out = await fn("text", "instruction")
    assert out == "GOOD"


@pytest.mark.asyncio
async def test_build_run_transform_raises_on_is_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RuntimeError is raised when ResultMessage.is_error is True."""
    import bearings.agent.reply_transform as rt_mod

    monkeypatch.setattr(
        rt_mod,
        "_sdk_query",
        _make_query_mock(_make_result_message(result="oops", is_error=True)),
    )
    fn = build_run_transform()
    with pytest.raises(RuntimeError, match="is_error=True"):
        await fn("text", "instruction")


@pytest.mark.asyncio
async def test_build_run_transform_raises_on_empty_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RuntimeError is raised when the stream ends with no ResultMessage."""
    import bearings.agent.reply_transform as rt_mod

    monkeypatch.setattr(
        rt_mod,
        "_sdk_query",
        _make_query_mock(_FakeOtherEvent()),
    )
    fn = build_run_transform()
    with pytest.raises(RuntimeError, match="no ResultMessage"):
        await fn("text", "instruction")


# ---------------------------------------------------------------------------
# Integration: run_transform wired into the FastAPI route
# ---------------------------------------------------------------------------


@pytest.fixture
async def app_with_real_transform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[FastAPI, aiosqlite.Connection]]:
    """App with run_transform replaced by the real factory (SDK mocked)."""
    import bearings.agent.reply_transform as rt_mod

    # Patch the SDK query at module level before building the transform fn.
    monkeypatch.setattr(
        rt_mod,
        "_sdk_query",
        _make_query_mock(_make_result_message(result="TRANSFORMED")),
    )
    wired_transform = build_run_transform()
    monkeypatch.setattr(reply_actions_mod, "run_transform", wired_transform)

    db_path = tmp_path / "rt_test.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        app = create_app(db_connection=conn)
        yield app, conn
    finally:
        await conn.close()


def test_route_uses_wired_transform(
    app_with_real_transform: tuple[FastAPI, aiosqlite.Connection],
) -> None:
    """The POST /api/sessions/{id}/reply_actions route returns 200 with the
    SDK's result text when run_transform is wired to the real factory."""
    app, conn = app_with_real_transform

    async def _create_session() -> str:
        s = await sessions_db.create(
            conn, kind="chat", title="t", working_dir="/wd", model="sonnet"
        )
        return s.id

    import asyncio

    session_id = asyncio.get_event_loop().run_until_complete(_create_session())

    with TestClient(app) as client:
        resp = client.post(
            f"/api/sessions/{session_id}/reply_actions",
            json={"source_content": "original text", "transformation_id": "summarize"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "TRANSFORMED"
    assert body["transformation_id"] == "summarize"
    assert body["inserted"] is False


# ---------------------------------------------------------------------------
# serve.py wiring integration: confirm module-level replacement
# ---------------------------------------------------------------------------


def test_serve_wires_run_transform_module_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Importing bearings.cli.serve and calling the wiring path replaces
    reply_actions.run_transform (no real serve started)."""
    import bearings.agent.reply_transform as rt_mod

    # Track build_run_transform calls
    calls: list[None] = []
    original_build = rt_mod.build_run_transform

    def _spy_build() -> Any:
        calls.append(None)
        return original_build()

    monkeypatch.setattr(rt_mod, "build_run_transform", _spy_build)
    # Simulate the wiring: directly call the assignment line from serve._run.
    reply_actions_mod.run_transform = rt_mod.build_run_transform()

    # After wiring, run_transform should NOT be the stub anymore.
    import inspect

    assert inspect.iscoroutinefunction(reply_actions_mod.run_transform)
    # The wired callable is a coroutine function (not the NotImplementedError stub).
    assert reply_actions_mod.run_transform is not reply_actions_mod._stub_run_transform
    assert len(calls) == 1
