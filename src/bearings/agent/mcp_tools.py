"""In-process MCP server Bearings registers on every SDK client it
builds. Exposes small tools the model can call to cooperate with the
token-cost mitigations shipped in Waves 2–3 of the plan at
`~/.claude/plans/enumerated-inventing-ullman.md`.

Current tool set:

  - ``bearings__get_tool_output(tool_use_id)`` — pulls the full
    persisted output of a prior tool call out of Bearings' SQLite DB.
    Paired with the PostToolUse hook in ``session.py`` that caps raw
    tool outputs in the model's context (``agent.tool_output_cap_chars``)
    and leaves behind an advisory pointer — "if you need the full
    text, call bearings__get_tool_output with this id." That turns a
    200k-char ``grep -r`` into an on-demand reference instead of a
    200k-char replay in every subsequent turn's cached input.

Closures over ``session_id`` + an injected ``db getter`` keep the
server stateless on disk. Callers (``AgentSession``) supply a callable
returning the current ``aiosqlite.Connection`` so a server built at
session-construction time survives reconnects that swap the underlying
DB handle (tests in particular). The connection is NEVER stored on the
server itself — only the getter.

Module is safe to import even in test environments that mock the SDK;
``build_bearings_mcp_server`` is the only public entry point and it
builds the server lazily when called.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import aiosqlite
from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from bearings.db import store

log = logging.getLogger(__name__)


# The MCP server name is the key the SDK routes tool calls under and
# the prefix the model sees on the full tool name. Using the short
# word avoids `mcp__bearings__get_tool_output` becoming a mouthful.
BEARINGS_MCP_SERVER_NAME = "bearings"

# Max chars returned by `get_tool_output` in a single call. Even
# though the DB can hold arbitrarily large outputs, round-tripping a
# 5 MB log through an MCP tool call would put us right back in the
# context-bloat scenario we're trying to avoid. 200 KB is enough for
# the realistic "I cut a grep too aggressively" cases; bigger outputs
# can be paginated in a future rev (not yet wired — callers just see
# the truncated head with an explicit "N more bytes" marker).
_GET_TOOL_OUTPUT_RETURN_CAP = 200_000


DbGetter = Callable[[], aiosqlite.Connection | None]


def _truncated_notice(full_len: int) -> str:
    """The trailing marker appended when a retrieved output exceeds
    the per-call return cap. Keeps the shape stable so the model can
    pattern-match and know to narrow the next query."""
    return (
        f"\n\n[bearings: output truncated — {full_len} total chars, "
        f"returned first {_GET_TOOL_OUTPUT_RETURN_CAP}. "
        "Narrow the original tool call (shorter path, head -n, smaller "
        "grep) if you need more than this head.]"
    )


def _format_not_found(tool_use_id: str) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"bearings: no tool call found with id {tool_use_id!r}. "
                    "The id must come verbatim from a prior tool_use in this "
                    "session — it is NOT a Bearings DB primary key. If you "
                    "just made the call, wait until after ToolCallEnd."
                ),
            }
        ],
        "is_error": True,
    }


def _format_wrong_session(tool_use_id: str) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"bearings: tool call {tool_use_id!r} belongs to a "
                    "different session. Only tool calls from THIS session "
                    "are retrievable via bearings__get_tool_output."
                ),
            }
        ],
        "is_error": True,
    }


def _format_no_output(tool_use_id: str, row: dict[str, Any]) -> dict[str, Any]:
    # Distinguish "still running" (no finished_at) from "completed with
    # empty body" (finished_at set, output NULL) — different failure
    # modes deserve different user-facing text so the model knows
    # whether a retry would help.
    if row.get("finished_at") is None:
        msg = (
            f"bearings: tool call {tool_use_id!r} has not finished yet. "
            "Wait for ToolCallEnd on this id, then retry."
        )
    else:
        msg = (
            f"bearings: tool call {tool_use_id!r} completed but stored no "
            "output (empty body or error-only result). Check the `error` "
            "field in the conversation if present."
        )
    return {"content": [{"type": "text", "text": msg}], "is_error": True}


def _build_get_tool_output(session_id: str, db_getter: DbGetter) -> Any:
    """Factory for the ``bearings__get_tool_output`` tool. Split out
    so the closure captures only what the handler needs — tests that
    assert handler shape can construct one without touching the SDK
    decorator's global registry."""

    @tool(
        "get_tool_output",
        (
            "Retrieve the FULL persisted output of a prior tool call in "
            "this Bearings session. Use when a previous tool output was "
            "truncated by the Bearings tool-output cap and you need the "
            "complete text. Accepts a tool_use_id from any prior tool_use "
            "block in this session. Returns the full output as text (or "
            "an error message if the id is unknown or still running)."
        ),
        {"tool_use_id": str},
    )
    async def get_tool_output(args: dict[str, Any]) -> dict[str, Any]:
        tool_use_id = str(args.get("tool_use_id") or "").strip()
        if not tool_use_id:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "bearings: tool_use_id is required and must be "
                            "the id string from a prior tool_use block."
                        ),
                    }
                ],
                "is_error": True,
            }
        db = db_getter()
        if db is None:
            # Should not happen in production — AgentSession only wires
            # this server when `db is not None`. Defensive for unit
            # tests that may stub a session without persistence.
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "bearings: DB not wired to this session, "
                            "tool-output retrieval is unavailable."
                        ),
                    }
                ],
                "is_error": True,
            }
        try:
            row = await store.get_tool_call(db, tool_use_id)
        except Exception:  # noqa: BLE001 — surface to model, not raise
            log.exception("bearings.get_tool_output: DB lookup failed for %s", tool_use_id)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "bearings: DB error retrieving the tool output. "
                            "Retry once; if it persists, ask the user."
                        ),
                    }
                ],
                "is_error": True,
            }
        if row is None:
            return _format_not_found(tool_use_id)
        if row.get("session_id") != session_id:
            return _format_wrong_session(tool_use_id)
        body = row.get("output")
        if not body:
            return _format_no_output(tool_use_id, row)
        full_len = len(body)
        if full_len > _GET_TOOL_OUTPUT_RETURN_CAP:
            body = body[:_GET_TOOL_OUTPUT_RETURN_CAP] + _truncated_notice(full_len)
        return {"content": [{"type": "text", "text": body}]}

    return get_tool_output


def build_bearings_mcp_server(session_id: str, db_getter: DbGetter) -> McpSdkServerConfig:
    """Construct the Bearings in-process MCP server for one session.

    Called from ``AgentSession.stream()`` on every turn so the tool
    set stays in lock-step with any future knobs we toggle per-turn
    (e.g. disabling `get_tool_output` under a hypothetical "no DB
    retrieval" profile). The cost is negligible — each tool is a
    lightweight closure, no subprocess or IPC.

    ``db_getter`` is called inside the tool handler, not at build
    time, so the returned server stays valid across DB reconnects."""
    tools: list[Any] = [_build_get_tool_output(session_id, db_getter)]
    return create_sdk_mcp_server(
        name=BEARINGS_MCP_SERVER_NAME,
        version="1.0.0",
        tools=tools,
    )


async def tool_output_char_len(body: Any) -> int:
    """Character length of a tool-output body, normalized across the
    shapes ``ToolResultBlock.content`` can carry.

    The SDK delivers `content` as either a plain ``str`` or a list of
    content blocks (dicts with ``type`` + ``text``). We care about the
    raw character count for the PostToolUse cap decision — a list of
    ten small text blocks with 100 chars each should compare equal to
    a single 1000-char string. Returns 0 for unrecognized shapes so a
    surprising payload never triggers a spurious cap.

    Coroutine on purpose so the hook can await it without special-
    casing (keeps the call site uniform even though the body is a
    trivial loop)."""
    if body is None:
        return 0
    if isinstance(body, str):
        return len(body)
    if isinstance(body, list):
        total = 0
        for block in body:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    total += len(text)
        return total
    return 0
