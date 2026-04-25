"""Tests for the in-process MCP server Bearings registers on every
SDK client (see `src/bearings/agent/mcp_tools.py`).

Covers the `bearings__get_tool_output` tool's happy path plus the
failure modes the handler has to distinguish (unknown id, wrong
session, still running, empty body). The PostToolUse advisory hook
that pairs with this tool is exercised in `test_agent_session.py`;
here we lock the retrieval side down."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from bearings.agent.mcp_tools import (
    _build_get_tool_output,
    build_bearings_mcp_server,
    tool_output_char_len,
)
from bearings.db import store
from bearings.db._common import init_db


@pytest.fixture
async def db(tmp_path: Path) -> Any:
    """Fresh schema per test — the MCP tool reads from `tool_calls`
    so every scenario needs its own rows."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        yield conn
    finally:
        await conn.close()


async def _seed_session_with_tool_call(
    db: Any,
    *,
    tool_call_id: str = "tc-1",
    output: str | None = "small output",
    error: str | None = None,
    finished: bool = True,
) -> str:
    """Helper: create a session and seed one tool_call row on it.
    Returns the session_id the MCP server should be scoped to."""
    sess = await store.create_session(db, working_dir="/tmp", model="m", title="t")
    sid = sess["id"]
    await store.insert_tool_call_start(
        db,
        session_id=sid,
        tool_call_id=tool_call_id,
        name="Bash",
        input_json='{"cmd": "x"}',
    )
    if finished:
        await store.finish_tool_call(db, tool_call_id=tool_call_id, output=output, error=error)
    return sid


@pytest.mark.asyncio
async def test_get_tool_output_returns_full_body(db: Any) -> None:
    """Happy path: id exists in THIS session, output is present and
    under the return cap — the handler returns the body verbatim."""
    sid = await _seed_session_with_tool_call(db, output="127.0.0.1 localhost")
    handler = _build_get_tool_output(sid, lambda: db).handler
    result = await handler({"tool_use_id": "tc-1"})
    assert result.get("is_error") is not True
    assert result["content"][0]["text"] == "127.0.0.1 localhost"


@pytest.mark.asyncio
async def test_get_tool_output_truncates_above_cap(db: Any) -> None:
    """Outputs larger than 200 KB get truncated with an explicit
    marker so the model isn't flooded with the same problem we're
    trying to solve."""
    big = "x" * 250_000
    sid = await _seed_session_with_tool_call(db, output=big)
    handler = _build_get_tool_output(sid, lambda: db).handler
    result = await handler({"tool_use_id": "tc-1"})
    text = result["content"][0]["text"]
    assert text.startswith("x" * 10)
    assert "[bearings: output truncated" in text
    assert "250000" in text


@pytest.mark.asyncio
async def test_get_tool_output_unknown_id_is_error(db: Any) -> None:
    sid = await _seed_session_with_tool_call(db)
    handler = _build_get_tool_output(sid, lambda: db).handler
    result = await handler({"tool_use_id": "bogus-id"})
    assert result["is_error"] is True
    assert "no tool call found" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_get_tool_output_wrong_session_rejected(db: Any) -> None:
    """Session scoping keeps one session from reading another's tool
    outputs. The SDK routes by server instance so cross-session leaks
    shouldn't be reachable in practice — this locks the belt-and-braces
    check in the handler itself."""
    # Seed on session A.
    await _seed_session_with_tool_call(db, tool_call_id="tc-a")
    # Build server scoped to a DIFFERENT session id.
    other_sid = "some-other-session"
    handler = _build_get_tool_output(other_sid, lambda: db).handler
    result = await handler({"tool_use_id": "tc-a"})
    assert result["is_error"] is True
    assert "belongs to a different session" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_get_tool_output_still_running(db: Any) -> None:
    """A row that exists but hasn't been finished yet → "not finished"
    error, not "no output" — the distinction matters because the model
    should retry after a ToolCallEnd rather than assume empty."""
    sid = await _seed_session_with_tool_call(db, finished=False)
    handler = _build_get_tool_output(sid, lambda: db).handler
    result = await handler({"tool_use_id": "tc-1"})
    assert result["is_error"] is True
    assert "not finished yet" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_get_tool_output_empty_body(db: Any) -> None:
    """Finished tool_call with NULL output → distinct "completed but
    empty" error so the model knows a retry won't help."""
    sid = await _seed_session_with_tool_call(db, output=None, finished=True)
    handler = _build_get_tool_output(sid, lambda: db).handler
    result = await handler({"tool_use_id": "tc-1"})
    assert result["is_error"] is True
    assert "stored no output" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_get_tool_output_rejects_empty_id() -> None:
    """Belt-and-braces: an empty / whitespace-only id bypasses the DB
    query entirely and returns a shape-error message."""
    handler = _build_get_tool_output("sess", lambda: None).handler
    result = await handler({"tool_use_id": ""})
    assert result["is_error"] is True
    assert "tool_use_id is required" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_get_tool_output_no_db_getter() -> None:
    """When the db-getter returns None (test fixture, error path), the
    handler fails closed with a helpful message rather than raising."""
    handler = _build_get_tool_output("sess", lambda: None).handler
    result = await handler({"tool_use_id": "tc-1"})
    assert result["is_error"] is True
    assert "DB not wired" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_build_bearings_mcp_server_exposes_tool(db: Any) -> None:
    """The public factory must produce an SDK McpSdkServerConfig whose
    server instance carries the get_tool_output tool."""
    sid = await _seed_session_with_tool_call(db)
    config = build_bearings_mcp_server(sid, lambda: db)
    # Exact shape check: McpSdkServerConfig is a TypedDict with
    # `type="sdk"`, `name`, and `instance`. The server exposes the
    # tool via `instance.list_tools()`; we just check the config
    # envelope and the name here — deeper behavior is covered by the
    # handler tests above, which bypass the server envelope.
    assert config["type"] == "sdk"
    assert config["name"] == "bearings"
    assert config["instance"] is not None


@pytest.mark.asyncio
async def test_tool_output_char_len_shapes() -> None:
    assert await tool_output_char_len(None) == 0
    assert await tool_output_char_len("hello") == 5
    blocks = [{"type": "text", "text": "abc"}, {"type": "text", "text": "de"}]
    assert await tool_output_char_len(blocks) == 5
    # Unknown shape → 0 so a surprising payload never triggers the cap
    # spuriously.
    assert await tool_output_char_len(12345) == 0
