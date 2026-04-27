"""Stream-event / block translation mixin for ``AgentSession``.

The methods here turn raw SDK objects (streaming-event dicts, content
blocks) into Bearings wire events (``Token`` / ``Thinking`` /
``ToolCallStart`` / ``ToolCallEnd``). Extracted from ``session.py``
(§FileSize); bodies unchanged.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import (
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from bearings.agent.events import (
    AgentEvent,
    Thinking,
    Token,
    ToolCallEnd,
    ToolCallStart,
)
from bearings.agent.session._helpers import _stringify


class _EventsMixin:
    """AgentSession methods that translate SDK payloads into wire
    events."""

    # Type-only attribute declaration (populated by AgentSession.__init__).
    session_id: str

    def _translate_stream_event(self, event: dict[str, Any]) -> AgentEvent | None:
        """Turn an Anthropic streaming event dict into a wire event.

        Only ``content_block_delta`` with ``text_delta`` /
        ``thinking_delta`` payloads are surfaced — other event kinds
        (message_start, content_block_start, input_json_delta, etc.)
        are ignored because the rest of the pipeline keys off the
        completed blocks in the trailing ``AssistantMessage``.
        """
        if event.get("type") != "content_block_delta":
            return None
        delta = event.get("delta") or {}
        delta_type = delta.get("type")
        if delta_type == "text_delta":
            text = delta.get("text") or ""
            return Token(session_id=self.session_id, text=text) if text else None
        if delta_type == "thinking_delta":
            text = delta.get("thinking") or ""
            return Thinking(session_id=self.session_id, text=text) if text else None
        return None

    def _translate_block(self, block: object) -> AgentEvent | None:
        if isinstance(block, TextBlock):
            return Token(session_id=self.session_id, text=block.text)
        if isinstance(block, ThinkingBlock):
            return Thinking(session_id=self.session_id, text=block.thinking)
        if isinstance(block, ToolUseBlock):
            return ToolCallStart(
                session_id=self.session_id,
                tool_call_id=block.id,
                name=block.name,
                input=dict(block.input),
            )
        if isinstance(block, ToolResultBlock):
            return self._tool_call_end(block)
        return None

    def _tool_call_end(self, block: ToolResultBlock) -> ToolCallEnd:
        is_error = bool(block.is_error)
        body = _stringify(block.content)
        return ToolCallEnd(
            session_id=self.session_id,
            tool_call_id=block.tool_use_id,
            ok=not is_error,
            output=None if is_error else body,
            error=body if is_error else None,
        )
