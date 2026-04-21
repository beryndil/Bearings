from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class UserMessage(BaseModel):
    type: Literal["user_message"] = "user_message"
    session_id: str
    content: str


class Token(BaseModel):
    type: Literal["token"] = "token"
    session_id: str
    text: str


class Thinking(BaseModel):
    type: Literal["thinking"] = "thinking"
    session_id: str
    text: str


class ToolCallStart(BaseModel):
    type: Literal["tool_call_start"] = "tool_call_start"
    session_id: str
    tool_call_id: str
    name: str
    input: dict[str, object] = Field(default_factory=dict)


class ToolCallEnd(BaseModel):
    type: Literal["tool_call_end"] = "tool_call_end"
    session_id: str
    tool_call_id: str
    ok: bool
    output: str | None = None
    error: str | None = None


class ToolOutputDelta(BaseModel):
    """Incremental chunk of tool output produced while a tool call is
    still running. Frontend reducer appends `delta` to the matching
    tool call's `output`. Deltas MUST be emitted before the final
    `ToolCallEnd` for the same `tool_call_id`; the reducer drops any
    delta whose target call is already finished. Sources that feed
    these events are expected to line-buffer (see
    `agent/line_buffer.py`) so chunks never split multibyte UTF-8
    codepoints or ANSI escape sequences mid-sequence."""

    type: Literal["tool_output_delta"] = "tool_output_delta"
    session_id: str
    tool_call_id: str
    delta: str


class MessageStart(BaseModel):
    type: Literal["message_start"] = "message_start"
    session_id: str
    message_id: str


class MessageComplete(BaseModel):
    type: Literal["message_complete"] = "message_complete"
    session_id: str
    message_id: str
    cost_usd: float | None = None
    # Per-turn token counts from ResultMessage.usage. Populated on real
    # completions (set of four non-negative ints); `None` on synthetic
    # completions emitted by a stop/cancel before the SDK reported
    # usage, so the reducer can distinguish "no data" from "zero use".
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    session_id: str
    message: str


class ApprovalRequest(BaseModel):
    """Tool-use permission request raised by the SDK's `can_use_tool`
    callback. Fired whenever the agent tries to use a tool that the
    current `permission_mode` gates — most visibly `ExitPlanMode` while
    in plan mode, but also any write-capable tool under a restrictive
    mode. The runner parks an `asyncio.Future` keyed by `request_id`
    and blocks until the frontend sends a matching
    `{type:"approval_response"}` frame, at which point the SDK is
    released with either `PermissionResultAllow` or `PermissionResultDeny`.
    Replays cleanly over the ring buffer so a mid-approval reconnect
    re-renders the modal."""

    type: Literal["approval_request"] = "approval_request"
    session_id: str
    request_id: str
    tool_name: str
    input: dict[str, object] = Field(default_factory=dict)
    tool_use_id: str | None = None


class ApprovalResolved(BaseModel):
    """Emitted when a pending approval is resolved (either by user
    click, by runner shutdown, or by `request_stop`). Frontend uses
    this to clear the modal on every connected tab so a second tab
    doesn't hold a stale pending prompt after the first tab answered."""

    type: Literal["approval_resolved"] = "approval_resolved"
    session_id: str
    request_id: str
    decision: Literal["allow", "deny"]


AgentEvent = (
    UserMessage
    | Token
    | Thinking
    | ToolCallStart
    | ToolCallEnd
    | ToolOutputDelta
    | MessageStart
    | MessageComplete
    | ErrorEvent
    | ApprovalRequest
    | ApprovalResolved
)
