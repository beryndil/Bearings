from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from bearings.agent.events import (
    ContextUsage,
    ErrorEvent,
    MessageComplete,
    MessageStart,
    Thinking,
    Token,
    ToolCallEnd,
    ToolCallStart,
)
from bearings.agent.session import AgentSession


def _result(
    session_id: str = "sdk-sess",
    total_cost_usd: float | None = None,
    usage: dict[str, Any] | None = None,
) -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id=session_id,
        total_cost_usd=total_cost_usd,
        usage=usage,
    )


def _assistant(*blocks: Any) -> AssistantMessage:
    return AssistantMessage(content=list(blocks), model="claude-sonnet-4-6")


class FakeClient:
    """Drop-in replacement for ClaudeSDKClient used in unit tests."""

    def __init__(self, messages: list[Any], options: Any = None) -> None:
        self._messages = messages
        self.options = options
        self.queried: list[str] = []

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def query(self, prompt: str) -> None:
        self.queried.append(prompt)

    async def receive_response(self) -> AsyncIterator[Any]:
        for msg in self._messages:
            yield msg


def _patch_client(monkeypatch: pytest.MonkeyPatch, messages: list[Any]) -> None:
    def factory(options: Any = None) -> FakeClient:
        return FakeClient(messages, options)

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)


def test_agent_session_constructs() -> None:
    session = AgentSession("abc", working_dir="/tmp", model="claude-opus-4-7")
    assert session.session_id == "abc"
    assert session.working_dir == "/tmp"
    assert session.model == "claude-opus-4-7"
    assert session.max_budget_usd is None


@pytest.mark.asyncio
async def test_stream_omits_budget_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class CapturingClient(FakeClient):
        def __init__(self, messages: list[Any], options: Any = None) -> None:
            super().__init__(messages, options)
            captured["options"] = options

    def factory(options: Any = None) -> CapturingClient:
        return CapturingClient([_result()], options)

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    session = AgentSession("s", working_dir="/tmp", model="m")
    _ = [ev async for ev in session.stream("hi")]
    opts = captured["options"]
    assert opts.max_budget_usd is None


@pytest.mark.asyncio
async def test_stream_passes_budget_to_options(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class CapturingClient(FakeClient):
        def __init__(self, messages: list[Any], options: Any = None) -> None:
            super().__init__(messages, options)
            captured["options"] = options

    def factory(options: Any = None) -> CapturingClient:
        return CapturingClient([_result()], options)

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    session = AgentSession("s", working_dir="/tmp", model="m", max_budget_usd=0.25)
    _ = [ev async for ev in session.stream("hi")]
    opts = captured["options"]
    assert opts.max_budget_usd == 0.25


@pytest.mark.asyncio
async def test_stream_passes_permission_mode_to_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class CapturingClient(FakeClient):
        def __init__(self, messages: list[Any], options: Any = None) -> None:
            super().__init__(messages, options)
            captured["options"] = options

    def factory(options: Any = None) -> CapturingClient:
        return CapturingClient([_result()], options)

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    session = AgentSession("s", working_dir="/tmp", model="m")
    session.set_permission_mode("plan")
    _ = [ev async for ev in session.stream("hi")]
    assert captured["options"].permission_mode == "plan"


@pytest.mark.asyncio
async def test_stream_passes_sdk_session_id_as_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class CapturingClient(FakeClient):
        def __init__(self, messages: list[Any], options: Any = None) -> None:
            super().__init__(messages, options)
            captured["options"] = options

    def factory(options: Any = None) -> CapturingClient:
        return CapturingClient([_result()], options)

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    session = AgentSession(
        "s",
        working_dir="/tmp",
        model="m",
        sdk_session_id="prior-sdk-xyz",
    )
    _ = [ev async for ev in session.stream("hi")]
    assert captured["options"].resume == "prior-sdk-xyz"


@pytest.mark.asyncio
async def test_stream_passes_thinking_config_to_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a ThinkingConfig is supplied, the SDK options must carry it
    through verbatim so extended thinking is requested from the CLI."""
    captured: dict[str, Any] = {}

    class CapturingClient(FakeClient):
        def __init__(self, messages: list[Any], options: Any = None) -> None:
            super().__init__(messages, options)
            captured["options"] = options

    def factory(options: Any = None) -> CapturingClient:
        return CapturingClient([_result()], options)

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    session = AgentSession(
        "s",
        working_dir="/tmp",
        model="m",
        thinking={"type": "adaptive"},
    )
    _ = [ev async for ev in session.stream("hi")]
    assert captured["options"].thinking == {"type": "adaptive"}


@pytest.mark.asyncio
async def test_stream_omits_thinking_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default (`thinking=None`) leaves the SDK's own default in place —
    no `thinking` key on the options dataclass."""
    captured: dict[str, Any] = {}

    class CapturingClient(FakeClient):
        def __init__(self, messages: list[Any], options: Any = None) -> None:
            super().__init__(messages, options)
            captured["options"] = options

    def factory(options: Any = None) -> CapturingClient:
        return CapturingClient([_result()], options)

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    session = AgentSession("s", working_dir="/tmp", model="m")
    _ = [ev async for ev in session.stream("hi")]
    assert captured["options"].thinking is None


@pytest.mark.asyncio
async def test_stream_captures_sdk_session_id_from_assistant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assistant = AssistantMessage(
        content=[TextBlock("hi")],
        model="claude-sonnet-4-6",
        session_id="new-sdk-abc",
    )
    _patch_client(monkeypatch, [assistant, _result()])
    session = AgentSession("s", working_dir="/tmp", model="m")
    _ = [ev async for ev in session.stream("hi")]
    assert session.sdk_session_id == "new-sdk-abc"


@pytest.mark.asyncio
async def test_stream_translates_text_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(
        monkeypatch,
        [_assistant(TextBlock("hello ")), _assistant(TextBlock("world")), _result()],
    )
    session = AgentSession("s1", working_dir="/tmp", model="claude-sonnet-4-6")
    events = [ev async for ev in session.stream("hi")]
    assert [type(e).__name__ for e in events] == [
        "MessageStart",
        "Token",
        "Token",
        "MessageComplete",
    ]
    start = events[0]
    complete = events[-1]
    assert isinstance(start, MessageStart)
    assert isinstance(complete, MessageComplete)
    assert start.session_id == "s1"
    assert len(start.message_id) == 32
    assert start.message_id == complete.message_id
    tokens = [e for e in events if isinstance(e, Token)]
    assert [t.text for t in tokens] == ["hello ", "world"]


@pytest.mark.asyncio
async def test_stream_translates_thinking_block(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(
        monkeypatch,
        [
            _assistant(
                ThinkingBlock(thinking="reasoning about the prompt", signature="sig"),
                TextBlock("answer"),
            ),
            _result(),
        ],
    )
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("hi")]
    types = [type(e).__name__ for e in events]
    assert types == ["MessageStart", "Thinking", "Token", "MessageComplete"]
    thinking = events[1]
    assert isinstance(thinking, Thinking)
    assert thinking.text == "reasoning about the prompt"


@pytest.mark.asyncio
async def test_stream_translates_tool_use_block(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = ToolUseBlock(id="tool-1", name="Read", input={"path": "/etc/hosts"})
    _patch_client(monkeypatch, [_assistant(TextBlock("looking..."), tool), _result()])
    session = AgentSession("s2", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("read it")]
    assert [type(e).__name__ for e in events] == [
        "MessageStart",
        "Token",
        "ToolCallStart",
        "MessageComplete",
    ]
    call = events[2]
    assert isinstance(call, ToolCallStart)
    assert call.tool_call_id == "tool-1"
    assert call.name == "Read"
    assert call.input == {"path": "/etc/hosts"}


@pytest.mark.asyncio
async def test_stream_translates_tool_result_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(
        monkeypatch,
        [
            _assistant(ToolUseBlock(id="t-1", name="Read", input={"path": "/x"})),
            UserMessage(
                content=[
                    ToolResultBlock(tool_use_id="t-1", content="file contents", is_error=False)
                ]
            ),
            _result(),
        ],
    )
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("read it")]
    types = [type(e).__name__ for e in events]
    assert types == ["MessageStart", "ToolCallStart", "ToolCallEnd", "MessageComplete"]
    end = events[2]
    assert isinstance(end, ToolCallEnd)
    assert end.tool_call_id == "t-1"
    assert end.ok is True
    assert end.output == "file contents"
    assert end.error is None


@pytest.mark.asyncio
async def test_stream_marks_tool_result_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(
        monkeypatch,
        [
            _assistant(ToolUseBlock(id="t-err", name="Bash", input={"cmd": "false"})),
            UserMessage(
                content=[ToolResultBlock(tool_use_id="t-err", content="exit 1", is_error=True)]
            ),
            _result(),
        ],
    )
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("run it")]
    end = next(e for e in events if isinstance(e, ToolCallEnd))
    assert end.ok is False
    assert end.error == "exit 1"
    assert end.output is None


@pytest.mark.asyncio
async def test_stream_stops_on_result_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(
        monkeypatch,
        [_assistant(TextBlock("pre")), _result(), _assistant(TextBlock("post"))],
    )
    session = AgentSession("s3", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("x")]
    tokens = [e for e in events if isinstance(e, Token)]
    assert [t.text for t in tokens] == ["pre"]


@pytest.mark.asyncio
async def test_stream_message_complete_carries_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(
        monkeypatch,
        [_assistant(TextBlock("hi")), _result(total_cost_usd=0.0042)],
    )
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("x")]
    complete = events[-1]
    assert isinstance(complete, MessageComplete)
    assert complete.cost_usd == pytest.approx(0.0042)


@pytest.mark.asyncio
async def test_stream_message_complete_cost_none_when_sdk_omits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, [_assistant(TextBlock("hi")), _result()])
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("x")]
    complete = events[-1]
    assert isinstance(complete, MessageComplete)
    assert complete.cost_usd is None


@pytest.mark.asyncio
async def test_stream_message_complete_carries_usage_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ResultMessage.usage` maps into the four token fields on
    `MessageComplete` under the shorter column names used in the DB.
    Cache fields in particular lose the `_input` suffix — a regression
    here means per-turn cache usage silently stops being persisted."""
    usage = {
        "input_tokens": 12,
        "output_tokens": 34,
        "cache_read_input_tokens": 56,
        "cache_creation_input_tokens": 78,
    }
    _patch_client(
        monkeypatch,
        [_assistant(TextBlock("hi")), _result(total_cost_usd=0.01, usage=usage)],
    )
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("x")]
    complete = events[-1]
    assert isinstance(complete, MessageComplete)
    assert complete.input_tokens == 12
    assert complete.output_tokens == 34
    assert complete.cache_read_tokens == 56
    assert complete.cache_creation_tokens == 78


@pytest.mark.asyncio
async def test_stream_message_complete_usage_none_leaves_tokens_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No usage on the ResultMessage → every token field stays None so
    the DB row carries NULL rather than a silently-fabricated zero."""
    _patch_client(monkeypatch, [_assistant(TextBlock("hi")), _result()])
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("x")]
    complete = events[-1]
    assert isinstance(complete, MessageComplete)
    assert complete.input_tokens is None
    assert complete.output_tokens is None
    assert complete.cache_read_tokens is None
    assert complete.cache_creation_tokens is None


def test_extract_tokens_returns_none_for_missing_keys() -> None:
    """Unknown/missing keys stay None so a future SDK reshape can't
    silently land bad zeros in the DB."""
    from bearings.agent.session import _extract_tokens

    got = _extract_tokens({"input_tokens": 5})
    assert got == {
        "input_tokens": 5,
        "output_tokens": None,
        "cache_read_tokens": None,
        "cache_creation_tokens": None,
    }


def test_extract_tokens_rejects_bool_values() -> None:
    """`bool` is a subclass of `int`, so a stray True from an upstream
    bug would round-trip as 1 without an explicit guard. Regression
    here means corrupted token counts on certain SDK bugs."""
    from bearings.agent.session import _extract_tokens

    got = _extract_tokens(
        {
            "input_tokens": True,
            "output_tokens": False,
            "cache_read_input_tokens": 7,
            "cache_creation_input_tokens": 8,
        }
    )
    assert got["input_tokens"] is None
    assert got["output_tokens"] is None
    assert got["cache_read_tokens"] == 7
    assert got["cache_creation_tokens"] == 8


def test_extract_tokens_none_usage_returns_all_none() -> None:
    """`None` usage (synthetic completions from stop/cancel) yields
    all-None so the DB row keeps NULLs and the frontend can tell
    "no data" from "zero use"."""
    from bearings.agent.session import _extract_tokens

    got = _extract_tokens(None)
    assert got == {
        "input_tokens": None,
        "output_tokens": None,
        "cache_read_tokens": None,
        "cache_creation_tokens": None,
    }


@pytest.mark.asyncio
async def test_interrupt_is_noop_when_no_active_stream() -> None:
    session = AgentSession("s", working_dir="/tmp", model="m")
    # Should not raise, should not error.
    await session.interrupt()
    assert session._client is None


@pytest.mark.asyncio
async def test_stream_tracks_client_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """While an in-flight stream is running, `_client` points at the
    active SDK client so `interrupt()` can reach it. After the stream
    completes naturally, the reference drops."""
    seen: dict[str, Any] = {"mid_stream": None}

    def factory(options: Any = None) -> FakeClient:
        return FakeClient([_assistant(TextBlock("hi")), _result()], options)

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    session = AgentSession("s", working_dir="/tmp", model="m")
    async for ev in session.stream("go"):
        # Capture on the first non-MessageStart event so we know we're
        # inside the `async with` body.
        if not isinstance(ev, MessageStart) and seen["mid_stream"] is None:
            seen["mid_stream"] = session._client
    # After the generator runs to completion, reference drops.
    assert session._client is None
    assert seen["mid_stream"] is not None


@pytest.mark.asyncio
async def test_interrupt_during_stream_calls_sdk_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mid-stream `session.interrupt()` forwards to the active SDK
    client's `interrupt()` method. That's what tells the CLI subprocess
    to abort a running tool — cancelling the iteration alone wouldn't
    stop the tool."""

    class InterruptTrackingClient(FakeClient):
        def __init__(self, messages: list[Any], options: Any = None) -> None:
            super().__init__(messages, options)
            self.interrupt_calls = 0

        async def interrupt(self) -> None:
            self.interrupt_calls += 1

    ref: dict[str, InterruptTrackingClient] = {}

    def factory(options: Any = None) -> InterruptTrackingClient:
        client = InterruptTrackingClient([_assistant(TextBlock("running")), _result()], options)
        ref["client"] = client
        return client

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    session = AgentSession("s", working_dir="/tmp", model="m")
    async for ev in session.stream("go"):
        if isinstance(ev, Token):
            await session.interrupt()
    assert ref["client"].interrupt_calls == 1


@pytest.mark.asyncio
async def test_stream_emits_error_event_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BoomClient(FakeClient):
        async def query(self, prompt: str) -> None:
            raise RuntimeError("kaboom")

    def factory(options: Any = None) -> BoomClient:
        return BoomClient([], options)

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    session = AgentSession("s4", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("x")]
    assert len(events) == 1
    err = events[0]
    assert isinstance(err, ErrorEvent)
    assert "kaboom" in err.message


def _text_delta(text: str, index: int = 0) -> StreamEvent:
    return StreamEvent(
        uuid="e",
        session_id="sdk-sess",
        event={
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "text_delta", "text": text},
        },
        parent_tool_use_id=None,
    )


def _thinking_delta(text: str, index: int = 0) -> StreamEvent:
    return StreamEvent(
        uuid="e",
        session_id="sdk-sess",
        event={
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "thinking_delta", "thinking": text},
        },
        parent_tool_use_id=None,
    )


@pytest.mark.asyncio
async def test_stream_event_emits_text_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    """StreamEvent text_delta fragments surface as Token events, and the
    trailing AssistantMessage's TextBlock is skipped to avoid a double
    emission."""
    _patch_client(
        monkeypatch,
        [
            _text_delta("Hel"),
            _text_delta("lo "),
            _text_delta("world"),
            _assistant(TextBlock("Hello world")),
            _result(),
        ],
    )
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("hi")]
    tokens = [e for e in events if isinstance(e, Token)]
    assert [t.text for t in tokens] == ["Hel", "lo ", "world"]
    # No duplicate from the AssistantMessage.
    assert len(tokens) == 3


@pytest.mark.asyncio
async def test_stream_event_emits_thinking_deltas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When both thinking and text stream via deltas, the matching blocks
    in the trailing AssistantMessage are skipped. Only same-kind skipping
    is allowed: a thinking_delta must not suppress a TextBlock (and vice
    versa)."""
    _patch_client(
        monkeypatch,
        [
            _thinking_delta("pondering "),
            _thinking_delta("the prompt"),
            _text_delta("the "),
            _text_delta("answer"),
            _assistant(
                ThinkingBlock(thinking="pondering the prompt", signature="sig"),
                TextBlock("the answer"),
            ),
            _result(),
        ],
    )
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("hi")]
    assert [type(e).__name__ for e in events] == [
        "MessageStart",
        "Thinking",
        "Thinking",
        "Token",
        "Token",
        "MessageComplete",
    ]
    thinking = [e for e in events if isinstance(e, Thinking)]
    assert [t.text for t in thinking] == ["pondering ", "the prompt"]
    tokens = [e for e in events if isinstance(e, Token)]
    assert [t.text for t in tokens] == ["the ", "answer"]


@pytest.mark.asyncio
async def test_thinking_block_surfaces_when_only_text_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: Opus 4.7 in adaptive-thinking mode emits text_delta
    events during streaming but NOT thinking_delta events — the thinking
    content only arrives as a ThinkingBlock in the final AssistantMessage.
    The per-block-type guard in stream() must suppress the TextBlock
    (already streamed) while still emitting the Thinking event for the
    ThinkingBlock (never streamed)."""
    _patch_client(
        monkeypatch,
        [
            _text_delta("the "),
            _text_delta("answer"),
            _assistant(
                ThinkingBlock(thinking="reasoning that never streamed", signature="sig"),
                TextBlock("the answer"),
            ),
            _result(),
        ],
    )
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("hi")]
    # Thinking comes from the final AssistantMessage; Tokens from deltas;
    # the TextBlock in the AssistantMessage is suppressed as a duplicate.
    assert [type(e).__name__ for e in events] == [
        "MessageStart",
        "Token",
        "Token",
        "Thinking",
        "MessageComplete",
    ]
    thinking = [e for e in events if isinstance(e, Thinking)]
    assert [t.text for t in thinking] == ["reasoning that never streamed"]


@pytest.mark.asyncio
async def test_stream_event_preserves_tool_use_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool-use blocks arrive complete in the AssistantMessage (deltas
    stream input JSON but we don't parse that). They must still be
    emitted even when text deltas preceded them."""
    _patch_client(
        monkeypatch,
        [
            _text_delta("calling "),
            _text_delta("a tool"),
            _assistant(
                TextBlock("calling a tool"),
                ToolUseBlock(id="t1", name="Read", input={"path": "/etc/hosts"}),
            ),
            _result(),
        ],
    )
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("hi")]
    types = [type(e).__name__ for e in events]
    assert types == [
        "MessageStart",
        "Token",
        "Token",
        "ToolCallStart",
        "MessageComplete",
    ]
    call = next(e for e in events if isinstance(e, ToolCallStart))
    assert call.tool_call_id == "t1"
    assert call.input == {"path": "/etc/hosts"}


@pytest.mark.asyncio
async def test_stream_event_ignores_non_delta_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-delta stream events (message_start, content_block_start,
    content_block_stop, input_json_delta, etc.) are dropped — they carry
    no user-visible content the pipeline needs."""
    noise = StreamEvent(
        uuid="e",
        session_id="sdk-sess",
        event={"type": "message_start", "message": {"id": "m1"}},
        parent_tool_use_id=None,
    )
    input_delta = StreamEvent(
        uuid="e",
        session_id="sdk-sess",
        event={
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"p":'},
        },
        parent_tool_use_id=None,
    )
    _patch_client(
        monkeypatch,
        [noise, input_delta, _assistant(TextBlock("hi")), _result()],
    )
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("x")]
    # No StreamEvent deltas surfaced, so streamed_this_msg stays False
    # and the TextBlock in the AssistantMessage emits normally.
    assert [type(e).__name__ for e in events] == [
        "MessageStart",
        "Token",
        "MessageComplete",
    ]


@pytest.mark.asyncio
async def test_stream_passes_assembled_system_prompt_when_db_wired(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """With db= set, stream() calls assemble_prompt and passes the
    result through as ClaudeAgentOptions.system_prompt. Without db=
    (the prior behavior), system_prompt stays None."""
    from bearings.agent.base_prompt import BASE_PROMPT
    from bearings.db.store import (
        attach_tag,
        create_session,
        create_tag,
        init_db,
        put_tag_memory,
        update_session,
    )

    captured: dict[str, Any] = {}

    class CapturingClient(FakeClient):
        def __init__(self, messages: list[Any], options: Any = None) -> None:
            super().__init__(messages, options)
            captured["options"] = options

    def factory(options: Any = None) -> CapturingClient:
        return CapturingClient([_result()], options)

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        sess = await create_session(conn, working_dir="/x", model="m")
        tag = await create_tag(conn, name="infra")
        await attach_tag(conn, sess["id"], tag["id"])
        await put_tag_memory(conn, tag["id"], "Prefer nftables.")
        await update_session(conn, sess["id"], fields={"session_instructions": "Be concise."})
        agent = AgentSession(sess["id"], working_dir="/x", model="m", db=conn)
        _ = [ev async for ev in agent.stream("hi")]
    finally:
        await conn.close()
    opts = captured["options"]
    assert opts.system_prompt is not None
    assert BASE_PROMPT in opts.system_prompt
    assert "Prefer nftables." in opts.system_prompt
    assert "Be concise." in opts.system_prompt


@pytest.mark.asyncio
async def test_stream_omits_system_prompt_when_db_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class CapturingClient(FakeClient):
        def __init__(self, messages: list[Any], options: Any = None) -> None:
            super().__init__(messages, options)
            captured["options"] = options

    def factory(options: Any = None) -> CapturingClient:
        return CapturingClient([_result()], options)

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    session = AgentSession("s", working_dir="/tmp", model="m")
    _ = [ev async for ev in session.stream("hi")]
    assert captured["options"].system_prompt is None


@pytest.mark.asyncio
async def test_stream_prepends_history_prefix_on_first_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """On the first stream() of a freshly-built AgentSession that has
    prior DB-persisted turns, the prompt passed to the SDK carries a
    `<previous-conversation>` preamble. This is the belt-and-suspenders
    backup for cases where `resume=<sdk_session_id>` fails to rehydrate
    context on the CLI side."""
    from bearings.db.store import create_session, init_db, insert_message

    captured: dict[str, FakeClient] = {}

    def factory(options: Any = None) -> FakeClient:
        client = FakeClient([_result()], options)
        captured["client"] = client
        return client

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        sess = await create_session(conn, working_dir="/x", model="m")
        await insert_message(
            conn,
            session_id=sess["id"],
            role="user",
            content="who were the US presidents 2000-2020?",
        )
        await insert_message(
            conn,
            session_id=sess["id"],
            role="assistant",
            content="Clinton, Bush, Obama, Trump.",
        )
        agent = AgentSession(sess["id"], working_dir="/x", model="m", db=conn)
        _ = [ev async for ev in agent.stream("remind me which of those were republicans")]
    finally:
        await conn.close()
    queried = captured["client"].queried
    assert len(queried) == 1
    primed = queried[0]
    assert "<previous-conversation>" in primed
    assert "Clinton, Bush, Obama, Trump." in primed
    assert "who were the US presidents 2000-2020?" in primed
    assert primed.endswith("remind me which of those were republicans")


@pytest.mark.asyncio
async def test_stream_skips_history_prefix_when_no_prior_turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """A brand-new session (no DB messages beyond the current turn's user
    row, which the runner inserts before calling stream()) must NOT emit
    a preamble — there's nothing to prime, and a preamble around an
    empty transcript would just waste tokens and confuse the model."""
    from bearings.db.store import create_session, init_db, insert_message

    captured: dict[str, FakeClient] = {}

    def factory(options: Any = None) -> FakeClient:
        client = FakeClient([_result()], options)
        captured["client"] = client
        return client

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        sess = await create_session(conn, working_dir="/x", model="m")
        # Simulate the runner's pre-stream insert of the current turn's
        # own user row. The priming code must recognize and drop this.
        await insert_message(conn, session_id=sess["id"], role="user", content="first prompt")
        agent = AgentSession(sess["id"], working_dir="/x", model="m", db=conn)
        _ = [ev async for ev in agent.stream("first prompt")]
    finally:
        await conn.close()
    queried = captured["client"].queried
    assert queried == ["first prompt"]


@pytest.mark.asyncio
async def test_stream_primes_only_once_per_instance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """The preamble is a one-shot: after the first stream() call, the
    instance's `_primed` flag is set and subsequent turns rely on the
    SDK's own context chain (`resume=` + CLI session file). Priming on
    every turn would duplicate history and waste tokens."""
    from bearings.db.store import create_session, init_db, insert_message

    captured: dict[str, list[FakeClient]] = {"clients": []}

    def factory(options: Any = None) -> FakeClient:
        client = FakeClient([_result()], options)
        captured["clients"].append(client)
        return client

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        sess = await create_session(conn, working_dir="/x", model="m")
        await insert_message(conn, session_id=sess["id"], role="user", content="hi there")
        await insert_message(conn, session_id=sess["id"], role="assistant", content="hello!")
        agent = AgentSession(sess["id"], working_dir="/x", model="m", db=conn)
        _ = [ev async for ev in agent.stream("turn 1")]
        _ = [ev async for ev in agent.stream("turn 2")]
    finally:
        await conn.close()
    first_prompt, second_prompt = (c.queried[0] for c in captured["clients"])
    assert "<previous-conversation>" in first_prompt
    assert "<previous-conversation>" not in second_prompt
    assert second_prompt == "turn 2"


@pytest.mark.asyncio
async def test_stream_no_priming_when_db_not_wired() -> None:
    """Without a db= connection on the AgentSession, `_build_history_prefix`
    short-circuits to None — no history source, nothing to prime. Unit
    tests that construct a bare AgentSession (no persistence) must still
    see their raw prompt on the wire."""
    session = AgentSession("s", working_dir="/tmp", model="m")
    prefix = await session._build_history_prefix("hi")
    assert prefix is None


@pytest.mark.asyncio
async def test_history_prefix_truncates_long_messages(tmp_path: Any) -> None:
    """A single assistant turn producing a novel-length response must
    not blow the first-turn token budget. Each message body is capped
    at `_HISTORY_PRIME_MAX_CHARS` with a visible truncation marker so
    the model knows it's seeing a partial."""
    from bearings.agent.session import _HISTORY_PRIME_MAX_CHARS
    from bearings.db.store import create_session, init_db, insert_message

    conn = await init_db(tmp_path / "db.sqlite")
    try:
        sess = await create_session(conn, working_dir="/x", model="m")
        huge = "A" * (_HISTORY_PRIME_MAX_CHARS * 3)
        await insert_message(conn, session_id=sess["id"], role="user", content="tell me about A")
        await insert_message(conn, session_id=sess["id"], role="assistant", content=huge)
        agent = AgentSession(sess["id"], working_dir="/x", model="m", db=conn)
        prefix = await agent._build_history_prefix("follow-up")
    finally:
        await conn.close()
    assert prefix is not None
    assert "…[truncated]" in prefix
    # The preamble envelope plus truncation marker add a bit of overhead;
    # pin an upper bound well below the raw body length to catch
    # regressions where truncation silently stops firing.
    assert len(prefix) < len(huge)


# ---- context-usage capture (Option 1 / migration 0013) ---------------


class _CtxClient(FakeClient):
    """FakeClient variant that answers `get_context_usage()` with a
    canned payload. The SDK's real response has a pile of fields we
    don't touch here; this fake returns only what `_capture_context_usage`
    actually reads so a future SDK shape-change gets caught by mypy on
    the real code path, not this fixture."""

    def __init__(
        self,
        messages: list[Any],
        options: Any = None,
        usage: dict[str, Any] | Exception | None = None,
    ) -> None:
        super().__init__(messages, options)
        self._usage = usage

    async def get_context_usage(self) -> dict[str, Any]:
        if isinstance(self._usage, Exception):
            raise self._usage
        if self._usage is None:
            raise AttributeError("no usage configured")
        return self._usage


@pytest.mark.asyncio
async def test_stream_emits_context_usage_before_message_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed turn yields ContextUsage right before MessageComplete
    so the runner (which breaks on MessageComplete) sees the event
    before it exits the stream loop. Field values track the SDK payload."""
    payload = {
        "totalTokens": 45000,
        "maxTokens": 200000,
        "percentage": 22.5,
        "model": "claude-sonnet-4-6",
        "isAutoCompactEnabled": True,
        "autoCompactThreshold": 175000,
    }

    def factory(options: Any = None) -> _CtxClient:
        return _CtxClient([_assistant(TextBlock("hi")), _result()], options, usage=payload)

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    session = AgentSession("s", working_dir="/tmp", model="claude-sonnet-4-6")
    events = [ev async for ev in session.stream("hi")]
    types = [type(e).__name__ for e in events]
    assert types == ["MessageStart", "Token", "ContextUsage", "MessageComplete"]
    ctx = events[-2]
    assert isinstance(ctx, ContextUsage)
    assert ctx.total_tokens == 45000
    assert ctx.max_tokens == 200000
    assert ctx.percentage == pytest.approx(22.5)
    assert ctx.is_auto_compact_enabled is True
    assert ctx.auto_compact_threshold == 175000


@pytest.mark.asyncio
async def test_stream_skips_context_usage_when_sdk_call_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `get_context_usage()` raises (older SDK, transport hiccup, CLI
    crash-on-exit), the turn still completes cleanly — no ContextUsage
    event, no propagated error. The meter is advisory; losing it must
    never take down a successful turn."""

    def factory(options: Any = None) -> _CtxClient:
        return _CtxClient(
            [_assistant(TextBlock("hi")), _result()],
            options,
            usage=RuntimeError("SDK refused the query"),
        )

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("hi")]
    types = [type(e).__name__ for e in events]
    assert types == ["MessageStart", "Token", "MessageComplete"]
    assert not any(isinstance(e, ContextUsage) for e in events)
    assert not any(isinstance(e, ErrorEvent) for e in events)


@pytest.mark.asyncio
async def test_stream_context_usage_tolerates_missing_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpectedly sparse SDK payload still yields an event — we
    zero-fill the missing numeric fields and default the flags. Better
    to render 0% than skip the meter entirely on an SDK quirk."""

    def factory(options: Any = None) -> _CtxClient:
        return _CtxClient([_assistant(TextBlock("hi")), _result()], options, usage={})

    monkeypatch.setattr("bearings.agent.session.ClaudeSDKClient", factory)
    session = AgentSession("s", working_dir="/tmp", model="m")
    events = [ev async for ev in session.stream("hi")]
    ctx_events = [e for e in events if isinstance(e, ContextUsage)]
    assert len(ctx_events) == 1
    ctx = ctx_events[0]
    assert ctx.total_tokens == 0
    assert ctx.max_tokens == 0
    assert ctx.percentage == 0.0
    assert ctx.is_auto_compact_enabled is False
    assert ctx.auto_compact_threshold is None
