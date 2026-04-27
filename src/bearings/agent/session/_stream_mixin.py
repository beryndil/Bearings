"""Per-turn ``stream()`` mixin for ``AgentSession``.

This module hosts the heavyweight ``stream()`` generator that drives a
single Claude turn end-to-end: register the in-process MCP server +
hooks via :func:`build_stream_options`, multiplex
``receive_response`` messages with streaming bash tool-output deltas,
translate SDK payloads to wire events, and emit the final
``MessageComplete``.

Extracted from ``session.py`` (§FileSize); body unchanged. The
option-building portion lives in :mod:`._options` so this module
fits the size cap.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import aiosqlite
from claude_agent_sdk import (
    AssistantMessage,
    CanUseTool,
    ClaudeSDKClient,
    PermissionMode,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ThinkingConfig,
    ToolResultBlock,
    UserMessage,
)

# Lazy package handle. Used inside ``stream()`` to instantiate the SDK
# client via the package attribute (re-exported in ``__init__.py``) so
# tests that monkeypatch ``bearings.agent.session.ClaudeSDKClient``
# still see their replacement land. The attribute on the package is a
# fresh lookup per call — the direct import above is for type hints
# only.
import bearings.agent.session as _session_pkg  # noqa: E402
from bearings.agent.events import (
    AgentEvent,
    ContextUsage,
    ErrorEvent,
    MessageComplete,
    MessageStart,
    Thinking,
    Token,
    ToolCallEnd,
    ToolCallStart,
    ToolOutputDelta,
)
from bearings.agent.session._constants import BASH_TOOL_SDK_NAME
from bearings.agent.session._helpers import _extract_tokens
from bearings.agent.session._options import build_stream_options


async def _drain_msgs(
    client: ClaudeSDKClient,
    shared: asyncio.Queue[tuple[str, Any]],
) -> None:
    """Drain ``client.receive_response()`` onto the shared multiplex
    queue. Hand-rolled rather than ``asyncio.as_completed`` because the
    receive loop is already an async iterator the SDK owns; we want to
    forward each message verbatim and emit a sentinel on exhaustion."""
    try:
        async for msg in client.receive_response():
            await shared.put(("msg", msg))
    except asyncio.CancelledError:
        # Cancelled when the main loop breaks out of the multiplex —
        # re-raise so the task winds down cleanly.
        raise
    except Exception as exc:  # noqa: BLE001 — surface to consumer
        await shared.put(("error", exc))
    finally:
        with contextlib.suppress(asyncio.QueueFull):
            shared.put_nowait(("done", None))


class _StreamMixin:
    """AgentSession methods that drive a single Claude turn."""

    # Type-only attribute declarations (populated by AgentSession.__init__).
    session_id: str
    working_dir: str
    model: str
    max_budget_usd: float | None
    permission_mode: PermissionMode | None
    sdk_session_id: str | None
    thinking: ThinkingConfig | None
    can_use_tool: CanUseTool | None
    setting_sources: list[str] | None
    inherit_mcp_servers: bool
    inherit_hooks: bool
    tool_output_cap_chars: int
    enable_bearings_mcp: bool
    enable_precompact_steering: bool
    enable_researcher_subagent: bool
    db: aiosqlite.Connection | None
    _client: ClaudeSDKClient | None
    _primed: bool

    # Sibling-mixin methods. Real implementations come via AgentSession's
    # multi-inheritance; the bodies here exist only to keep mypy strict
    # happy and to fail loudly if the inheritance order ever inverts.
    _MIXIN_NOT_BOUND = (
        "Mixin stub called directly. AgentSession must inherit "
        "_HistoryMixin / _HooksMixin / _EventsMixin before "
        "_StreamMixin so MRO resolves real implementations first."
    )

    def _current_db(self) -> aiosqlite.Connection | None:
        raise NotImplementedError(self._MIXIN_NOT_BOUND)

    def _build_post_tool_use_hook(self) -> Any:
        raise NotImplementedError(self._MIXIN_NOT_BOUND)

    def _build_precompact_hook(self) -> Any:
        raise NotImplementedError(self._MIXIN_NOT_BOUND)

    async def _build_history_prefix(self, prompt: str) -> str | None:
        raise NotImplementedError(self._MIXIN_NOT_BOUND)

    async def _build_context_pressure_block(self) -> str | None:
        raise NotImplementedError(self._MIXIN_NOT_BOUND)

    async def _capture_context_usage(self, client: ClaudeSDKClient) -> ContextUsage | None:
        raise NotImplementedError(self._MIXIN_NOT_BOUND)

    def _translate_stream_event(self, event: dict[str, Any]) -> AgentEvent | None:
        raise NotImplementedError(self._MIXIN_NOT_BOUND)

    def _translate_block(self, block: object) -> AgentEvent | None:
        raise NotImplementedError(self._MIXIN_NOT_BOUND)

    def _tool_call_end(self, block: ToolResultBlock) -> ToolCallEnd:
        raise NotImplementedError(self._MIXIN_NOT_BOUND)

    async def stream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        options, prompt, delta_queue, pending_bash_ids = await build_stream_options(self, prompt)
        message_id = uuid4().hex
        cost_usd: float | None = None
        usage: dict[str, Any] | None = None
        context_event: ContextUsage | None = None

        # Resolve via the package namespace so test monkeypatches of
        # `bearings.agent.session.ClaudeSDKClient` take effect; the
        # top-level import is retained for type hints only.
        sdk_client_cls: type[ClaudeSDKClient] = _session_pkg.ClaudeSDKClient
        try:
            async with sdk_client_cls(options=options) as client:
                self._client = client
                drain_task: asyncio.Task[None] | None = None
                try:
                    await client.query(prompt)
                    yield MessageStart(session_id=self.session_id, message_id=message_id)
                    # Single multiplex queue: receive_response messages
                    # AND streaming tool-output deltas land here. The
                    # bash handler put-no-waits onto the same channel
                    # via the `delta_queue` shared with emit_delta_cb.
                    shared: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
                    drain_task = asyncio.create_task(_drain_msgs(client, shared))
                    # Track per-block-type streaming. Opus 4.7 in
                    # adaptive mode emits text_delta but NOT
                    # thinking_delta — the thinking content only
                    # arrives in the final AssistantMessage's
                    # ThinkingBlock. A single streamed_this_msg flag
                    # would drop that thinking block as a "duplicate"
                    # because text_delta fired. Track each block type
                    # independently so we only suppress the kind we
                    # actually saw streamed.
                    streamed_text = False
                    streamed_thinking = False
                    finished = False
                    while not finished:
                        # Drain any tool-output deltas first so a fast
                        # bash command's lines can't pile up behind a
                        # slow receive_response. ``get_nowait`` is the
                        # right primitive: when there are no deltas,
                        # we fall through to an awaitable shared.get().
                        flushed_delta = False
                        while True:
                            try:
                                yield delta_queue.get_nowait()
                                flushed_delta = True
                            except asyncio.QueueEmpty:
                                break
                        if flushed_delta:
                            # Yield once more so deltas published in
                            # bursts can drain without blocking on a
                            # message that might not arrive for a while.
                            await asyncio.sleep(0)
                        # Wait on EITHER a fresh delta OR the next
                        # multiplexed message. Whichever lands first
                        # wins the iteration.
                        delta_get: asyncio.Task[ToolOutputDelta] = asyncio.create_task(
                            delta_queue.get()
                        )
                        shared_get: asyncio.Task[tuple[str, Any]] = asyncio.create_task(
                            shared.get()
                        )
                        pending: set[asyncio.Task[Any]] = {delta_get, shared_get}
                        try:
                            done, pending = await asyncio.wait(
                                pending,
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                        finally:
                            for task in (delta_get, shared_get):
                                if not task.done():
                                    task.cancel()
                                    with contextlib.suppress(asyncio.CancelledError):
                                        await task
                        for task in done:
                            if task is delta_get:
                                # delta_queue.get() returns ToolOutputDelta
                                yield delta_get.result()
                                continue
                            # The other branch is shared.get() returning
                            # ("kind", payload). Read off the typed
                            # task to keep mypy happy with the union.
                            kind, payload = shared_get.result()
                            if kind == "delta":
                                # Bash handler pushes onto delta_queue
                                # directly; this branch covers a future
                                # producer that wants to push through
                                # `shared`. Harmless either way.
                                if isinstance(payload, ToolOutputDelta):
                                    yield payload
                                continue
                            if kind == "done":
                                finished = True
                                continue
                            if kind == "error":
                                if isinstance(payload, BaseException):
                                    raise payload
                                continue
                            msg = payload
                            if isinstance(msg, StreamEvent):
                                event = self._translate_stream_event(msg.event)
                                if event is not None:
                                    if isinstance(event, Token):
                                        streamed_text = True
                                    elif isinstance(event, Thinking):
                                        streamed_thinking = True
                                    yield event
                            elif isinstance(msg, AssistantMessage):
                                if msg.session_id:
                                    self.sdk_session_id = msg.session_id
                                for block in msg.content:
                                    if streamed_text and isinstance(block, TextBlock):
                                        continue
                                    if streamed_thinking and isinstance(block, ThinkingBlock):
                                        continue
                                    event = self._translate_block(block)
                                    if event is None:
                                        continue
                                    # Pre-register bash tool_use_ids
                                    # for the side-channel correlator
                                    # before yielding so the handler
                                    # can claim the right id when the
                                    # SDK invokes call_tool.
                                    if (
                                        isinstance(event, ToolCallStart)
                                        and event.name == BASH_TOOL_SDK_NAME
                                    ):
                                        with contextlib.suppress(asyncio.QueueFull):
                                            pending_bash_ids.put_nowait(event.tool_call_id)
                                    yield event
                                streamed_text = False
                                streamed_thinking = False
                            elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                                for block in msg.content:
                                    if isinstance(block, ToolResultBlock):
                                        yield self._tool_call_end(block)
                            elif isinstance(msg, ResultMessage):
                                cost_usd = msg.total_cost_usd
                                usage = msg.usage
                                finished = True
                    # Drain any deltas that landed between the final
                    # multiplex iteration and now (a fast bash command
                    # whose last line raced the ResultMessage).
                    while True:
                        try:
                            yield delta_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    # Capture the context-usage snapshot while the CLI
                    # subprocess is still live. The async-with exit
                    # below tears it down; calling afterward would hit
                    # a closed connection.
                    context_event = await self._capture_context_usage(client)
                finally:
                    if drain_task is not None and not drain_task.done():
                        drain_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await drain_task
                    self._client = None
            # Yield the context-usage snapshot *before* MessageComplete
            # because the runner's stream loop breaks on MessageComplete
            # to persist the turn — anything after that is dropped on
            # the floor. The frontend reducer handles the two events on
            # independent state slots (fringe vs. meter) so ordering
            # doesn't create a visible glitch.
            if context_event is not None:
                yield context_event
            tokens = _extract_tokens(usage)
            yield MessageComplete(
                session_id=self.session_id,
                message_id=message_id,
                cost_usd=cost_usd,
                input_tokens=tokens["input_tokens"],
                output_tokens=tokens["output_tokens"],
                cache_read_tokens=tokens["cache_read_tokens"],
                cache_creation_tokens=tokens["cache_creation_tokens"],
            )
        except Exception as exc:  # noqa: BLE001 — surface as a wire event
            yield ErrorEvent(session_id=self.session_id, message=str(exc))
