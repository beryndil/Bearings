"""Smoke tests for :mod:`bearings.agent.events` — the AgentEvent
type surface item 1.1 lays for item 1.2 to plumb.

The actual streaming emission + per-event translation is owned by
``agent/translate.py`` (item 1.2); these tests exercise the
construction surface so a typo on a field name or a discriminator
literal cannot land silently.

Per arch §4.7, the discriminator is the ``type`` field. Tests build
one instance per event class, verify the discriminator literal, and
parse-roundtrip a representative subset through the discriminated-
union ``TypeAdapter`` so the union actually resolves to the right
variant.
"""

from __future__ import annotations

from pydantic import TypeAdapter

from bearings.agent.events import (
    AgentEvent,
    ApprovalRequest,
    ApprovalResolved,
    ContextUsage,
    ErrorEvent,
    MessageComplete,
    MessageStart,
    RoutingBadge,
    Thinking,
    TodoWriteUpdate,
    Token,
    ToolCallEnd,
    ToolCallStart,
    ToolOutputDelta,
    ToolProgress,
    TurnReplayed,
    UserMessage,
)

_AGENT_EVENT_ADAPTER: TypeAdapter[AgentEvent] = TypeAdapter(AgentEvent)


def test_user_message_constructs_and_carries_discriminator() -> None:
    ev = UserMessage(session_id="s1", message_id="m1", content="hello")
    assert ev.type == "user_message"
    assert ev.session_id == "s1"


def test_token_event() -> None:
    ev = Token(session_id="s1", message_id="m1", delta="he")
    assert ev.type == "token"
    assert ev.delta == "he"


def test_thinking_event() -> None:
    ev = Thinking(session_id="s1", message_id="m1", delta="...")
    assert ev.type == "thinking"


def test_tool_call_start_event() -> None:
    ev = ToolCallStart(
        session_id="s1",
        message_id="m1",
        tool_call_id="t1",
        tool_name="Read",
        tool_input_json='{"path": "/tmp/x"}',
    )
    assert ev.type == "tool_call_start"
    assert ev.tool_name == "Read"


def test_tool_output_delta_event() -> None:
    ev = ToolOutputDelta(session_id="s1", tool_call_id="t1", delta="line\n")
    assert ev.type == "tool_output_delta"


def test_tool_call_end_event_with_error() -> None:
    ev = ToolCallEnd(
        session_id="s1",
        message_id="m1",
        tool_call_id="t1",
        ok=False,
        duration_ms=120,
        output_summary="failed",
        error_message="permission denied",
    )
    assert ev.type == "tool_call_end"
    assert ev.error_message == "permission denied"


def test_tool_progress_event() -> None:
    ev = ToolProgress(session_id="s1", tool_call_id="t1", elapsed_ms=2500)
    assert ev.type == "tool_progress"


def test_message_start_event() -> None:
    ev = MessageStart(session_id="s1", message_id="m1")
    assert ev.type == "message_start"


def test_message_complete_carries_per_model_usage() -> None:
    ev = MessageComplete(
        session_id="s1",
        message_id="m1",
        content="hi",
        executor_input_tokens=100,
        executor_output_tokens=20,
        advisor_input_tokens=50,
        advisor_output_tokens=10,
        advisor_calls_count=1,
        cache_read_tokens=0,
    )
    assert ev.type == "message_complete"
    assert ev.executor_input_tokens == 100
    assert ev.advisor_calls_count == 1


def test_message_complete_legacy_fields_default_none() -> None:
    ev = MessageComplete(session_id="s1", message_id="m1", content="hi")
    assert ev.input_tokens is None
    assert ev.output_tokens is None
    assert ev.advisor_calls_count == 0


def test_routing_badge_event() -> None:
    ev = RoutingBadge(
        session_id="s1",
        message_id="m1",
        executor_model="sonnet",
        advisor_model="opus",
        advisor_calls_count=2,
        effort_level="auto",
        routing_source="tag_rule",
        routing_reason="bearings/architect tag",
    )
    assert ev.type == "routing_badge"
    assert ev.advisor_calls_count == 2


def test_context_usage_event() -> None:
    ev = ContextUsage(session_id="s1", percentage=42.5, total_tokens=85_000, max_tokens=200_000)
    assert ev.type == "context_usage"
    assert ev.total_tokens == 85_000


def test_error_event() -> None:
    ev = ErrorEvent(session_id="s1", message="rate limited", fatal=True)
    assert ev.type == "error"
    assert ev.fatal is True


def test_turn_replayed_event() -> None:
    ev = TurnReplayed(session_id="s1", message_id="m1")
    assert ev.type == "turn_replayed"


def test_approval_request_event() -> None:
    ev = ApprovalRequest(
        session_id="s1",
        request_id="r1",
        tool_name="Bash",
        tool_input_json='{"command": "rm -rf /"}',
    )
    assert ev.type == "approval_request"


def test_approval_resolved_event() -> None:
    ev = ApprovalResolved(session_id="s1", request_id="r1", approved=False)
    assert ev.type == "approval_resolved"
    assert ev.approved is False


def test_todo_write_update_event() -> None:
    ev = TodoWriteUpdate(session_id="s1", todos_json="[]")
    assert ev.type == "todo_write_update"


# ---------------------------------------------------------------------------
# Discriminated-union resolution
# ---------------------------------------------------------------------------


def test_union_resolves_token_variant() -> None:
    """Pydantic's discriminated-union picks ``Token`` from a ``type``
    field at parse time."""
    parsed = _AGENT_EVENT_ADAPTER.validate_python(
        {"type": "token", "session_id": "s1", "message_id": "m1", "delta": "x"}
    )
    assert isinstance(parsed, Token)


def test_union_resolves_routing_badge_variant() -> None:
    parsed = _AGENT_EVENT_ADAPTER.validate_python(
        {
            "type": "routing_badge",
            "session_id": "s1",
            "message_id": "m1",
            "executor_model": "sonnet",
            "advisor_model": "opus",
            "advisor_calls_count": 1,
            "effort_level": "auto",
            "routing_source": "tag_rule",
            "routing_reason": "test",
        }
    )
    assert isinstance(parsed, RoutingBadge)


def test_events_are_immutable() -> None:
    """Per :class:`_BaseEvent`'s ``frozen=True`` config, instances
    refuse mutation post-construction."""
    import pytest as _pytest  # local import keeps the module top-level tidy

    ev = Token(session_id="s1", message_id="m1", delta="x")
    with _pytest.raises(Exception):  # ValidationError variant
        ev.delta = "y"


def test_extra_fields_forbidden() -> None:
    """``extra='forbid'`` rejects unknown fields at the wire boundary."""
    import pytest as _pytest

    with _pytest.raises(Exception):  # ValidationError variant
        _AGENT_EVENT_ADAPTER.validate_python(
            {
                "type": "token",
                "session_id": "s1",
                "message_id": "m1",
                "delta": "x",
                "rogue_field": True,
            }
        )
