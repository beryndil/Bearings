# mypy: disable-error-code=explicit-any
"""SDK worker loop — drains the prompt queue and drives one full turn per prompt.

Per Slice A1 of ``~/.claude/plans/wiring-agent-loop.md``: this module bridges
the prompt-queue surface (item 1.7) to a live :class:`ClaudeSDKClient`.  The
SDK client is **persistent per session** — held open across turns via a single
``async with`` block.

Helpers extracted from this module:

* ``sdk_loop_errors.py``  — ``_enter_error_state``, ``_to_sdk_options``,
  ``_make_todo_update`` (and future 401-retry logic from Exec-2B).
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
from typing import Any

from claude_agent_sdk import ClaudeSDKClient, ResultMessage

from bearings.agent.analytics_capture import capture_turn
from bearings.agent.events import (
    ToolCallEnd,
    ToolCallStart,
    TurnStopped,
    UserMessage,
)
from bearings.agent.options import OptionsKwargs
from bearings.agent.persistence import (
    MessagePersistence,
    extract_model_usage,
    persist_assistant_turn,
)
from bearings.agent.runner import (
    QueuedPrompt,
    RunnerStatus,
    SessionRunner,
)
from bearings.agent.sdk_loop_errors import (
    TokenExpiredError,
    _enter_error_state,
    _is_auth_error,
    _is_init_timeout_error,
    _make_todo_update,
    _reload_sdk_credentials,
    _to_sdk_options,
    is_auth_result,
)
from bearings.agent.sdk_session_id import bearings_to_sdk_uuid
from bearings.agent.session import (
    AgentSession,
    SessionState,
    SessionStateError,
)
from bearings.agent.translate import SDKEventTranslator
from bearings.config.constants import (
    FORCE_ADVISOR_INSTRUCTION,
    INIT_TIMEOUT_AUTO_RECOVER_MAX,
    INIT_TIMEOUT_MAX_RETRIES,
    INIT_TIMEOUT_RETRY_BASE_DELAY_S,
)
from bearings.db import tool_calls as tool_calls_db
from bearings.db.tool_calls import ToolCallRecord

_log = logging.getLogger(__name__)

# ``BaseException`` covers ``asyncio.CancelledError`` (which inherits from
# ``BaseException``, not ``Exception``) and ``KeyboardInterrupt``.
import asyncio as _asyncio_mod  # noqa: E402

_CancelledLike: tuple[type[BaseException], ...] = (_asyncio_mod.CancelledError,)


async def _run_sdk_client_body(
    factory: Any,
    sdk_options: Any,
    runner: SessionRunner,
    session: AgentSession,
    translator: SDKEventTranslator,
    persist_fn: MessagePersistence,
) -> None:
    """Open one SDK client context and drain the prompt queue until cancelled.

    Extracted so :func:`run_session_loop` can call it twice — once on the
    first attempt and once on the 401-credential-reload retry — without
    duplicating the attach / detach bookkeeping.
    """
    async with factory(options=sdk_options) as client:
        session.attach_sdk_client(client)
        try:
            if session.state is SessionState.INITIALIZING:
                await session.start()
            await _drain_prompt_queue(runner, session, client, translator, persist_fn)
        finally:
            session.detach_sdk_client()


async def _handle_auth_error(
    exc: Exception,
    factory: Any,
    sdk_options: Any,
    runner: SessionRunner,
    session: AgentSession,
    translator: SDKEventTranslator,
    persist_fn: MessagePersistence,
) -> None:
    """Handle a first-401 auth error: check token freshness and retry once.

    If the OAuth token is fully expired, surfaces
    :class:`~bearings.agent.sdk_loop_errors.TokenExpiredError` immediately.
    If the token was merely rotated mid-flight, reloads it and retries the
    SDK client body once.  A second consecutive 401 on retry is fatal.
    """
    try:
        _reload_sdk_credentials()
    except TokenExpiredError as expired_exc:
        await _enter_error_state(runner, session, expired_exc)
        return
    # Token was recently rotated; fresh bearer is in the file.  Retry once.
    try:
        await _run_sdk_client_body(factory, sdk_options, runner, session, translator, persist_fn)
    except _CancelledLike:
        raise
    except Exception as retry_exc:
        await _enter_error_state(runner, session, retry_exc)


async def _handle_init_timeout(
    session_id: str,
    factory: Any,
    sdk_options: Any,
    runner: SessionRunner,
    session: AgentSession,
    translator: SDKEventTranslator,
    persist_fn: MessagePersistence,
) -> None:
    """Retry the SDK body up to INIT_TIMEOUT_MAX_RETRIES times on a handshake timeout.

    Transient under load (system stress, MCP warmup).  Uses exponential
    backoff between attempts.  On exhaustion, enters the error state and
    schedules an auto-recover if within the auto-recover cap.
    """
    for attempt in range(1, INIT_TIMEOUT_MAX_RETRIES + 1):
        delay = INIT_TIMEOUT_RETRY_BASE_DELAY_S * (2 ** (attempt - 1))
        _log.warning(
            "session %s: SDK initialize handshake timed out "
            "(attempt %d/%d) — retrying after %.0f s",
            session_id,
            attempt,
            INIT_TIMEOUT_MAX_RETRIES,
            delay,
        )
        await asyncio.sleep(delay)
        try:
            await _run_sdk_client_body(
                factory, sdk_options, runner, session, translator, persist_fn
            )
            return  # retry succeeded
        except _CancelledLike:
            raise
        except Exception as retry_exc:
            if not _is_init_timeout_error(retry_exc):
                await _enter_error_state(runner, session, retry_exc)
                return
            if attempt == INIT_TIMEOUT_MAX_RETRIES:
                await _enter_error_state(runner, session, retry_exc)
                scheduled = runner.schedule_auto_recover(INIT_TIMEOUT_AUTO_RECOVER_MAX)
                if not scheduled:
                    _log.warning(
                        "session %s: init-timeout auto-recover cap reached "
                        "(%d/%d) — manual /recover required",
                        session_id,
                        runner._auto_recover_attempts,
                        INIT_TIMEOUT_AUTO_RECOVER_MAX,
                    )
                return


async def run_session_loop(
    runner: SessionRunner,
    session: AgentSession,
    options_kwargs: OptionsKwargs,
    *,
    persist: MessagePersistence | None = None,
    client_factory: Any = None,
) -> None:
    """Run the SDK worker loop until the supervisor cancels.

    On a first ``"Invalid authentication credentials"`` (401) error the loop
    checks whether the OAuth token in ``~/.claude/.credentials.json`` is
    expired.  If it is, :class:`~bearings.agent.sdk_loop_errors.TokenExpiredError`
    is raised immediately with an actionable re-auth message — retrying with a
    known-stale bearer would only produce a second 401.  If the token is still
    valid (a mid-flight rotation), the loop closes the current subprocess,
    spawns a fresh one that reads the updated credentials file, and retries
    once.  A second consecutive 401 after a valid-token retry surfaces as a
    terminal error (``_enter_error_state``).

    Args:
        runner: Per-session :class:`SessionRunner` (prompt queue + ring buffer).
        session: :class:`AgentSession` carrying the lifecycle state machine.
        options_kwargs: Fully-composed :class:`OptionsKwargs` from
            :func:`bearings.agent.options.compose_session_options`.
        persist: Optional override for assistant-row persistence (test hook).
        client_factory: Optional override for :class:`ClaudeSDKClient` (test hook).
    """
    persist_fn: MessagePersistence = persist if persist is not None else persist_assistant_turn
    factory = client_factory if client_factory is not None else ClaudeSDKClient
    sdk_options = _to_sdk_options(options_kwargs)
    session_id = session.config.session_id

    def _log_cli_stderr(line: str, _sid: str = session_id) -> None:
        _log.warning("session %s: claude-cli stderr: %s", _sid, line.rstrip())

    sdk_options = dataclasses.replace(sdk_options, stderr=_log_cli_stderr)
    decision = session.config.decision
    translator = SDKEventTranslator(session.config.session_id, decision)
    try:
        await _run_sdk_client_body(factory, sdk_options, runner, session, translator, persist_fn)
    except _CancelledLike:
        raise
    except Exception as exc:
        if _is_auth_error(exc):
            await _handle_auth_error(
                exc, factory, sdk_options, runner, session, translator, persist_fn
            )
            return
        if _is_init_timeout_error(exc):
            await _handle_init_timeout(
                session_id, factory, sdk_options, runner, session, translator, persist_fn
            )
            return
        await _enter_error_state(runner, session, exc)


async def _drain_prompt_queue(
    runner: SessionRunner,
    session: AgentSession,
    client: ClaudeSDKClient,
    translator: SDKEventTranslator,
    persist_fn: MessagePersistence,
) -> None:
    """Inner pump: pop a prompt → run a turn → repeat."""
    while True:
        prompt = runner.pop_next_prompt()
        if prompt is None:
            runner.set_status(
                RunnerStatus(
                    is_running=False,
                    is_awaiting_user=True,
                    routing_decision=session.config.decision,
                )
            )
            await runner.new_prompt_event.wait()
            continue
        await _run_one_turn(runner, session, client, translator, persist_fn, prompt)


async def _stop_watcher(runner: SessionRunner, session: AgentSession) -> None:
    """Await the runner's stop event and forward an interrupt to the SDK.

    Spawned as a background task at the start of each turn by
    :func:`_run_one_turn`.  :class:`SessionStateError` is suppressed: the
    session may have already transitioned to CLOSED or ERROR by the time the
    interrupt fires.
    """
    await runner.stop_event.wait()
    with contextlib.suppress(SessionStateError):
        await session.interrupt()


async def _run_one_turn(
    runner: SessionRunner,
    session: AgentSession,
    client: ClaudeSDKClient,
    translator: SDKEventTranslator,
    persist_fn: MessagePersistence,
    prompt: QueuedPrompt,
) -> None:
    """Drive one full SDK turn end-to-end."""
    runner.stop_event.clear()
    stop_task: asyncio.Task[None] = asyncio.create_task(
        _stop_watcher(runner, session),
        name=f"stop_watcher:{runner.session_id}",
    )
    try:
        await _do_run_one_turn(runner, session, client, translator, persist_fn, prompt)
    finally:
        stop_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stop_task


async def _collect_turn_events(
    runner: SessionRunner,
    client: ClaudeSDKClient,
    translator: SDKEventTranslator,
) -> tuple[ResultMessage | None, list[ToolCallStart], dict[str, ToolCallEnd]]:
    """Drain one SDK turn, emitting events and collecting tool-call bookkeeping.

    Returns ``(last_result, pending_starts, pending_ends)``.
    """
    last_result: ResultMessage | None = None
    pending_starts: list[ToolCallStart] = []
    pending_ends: dict[str, ToolCallEnd] = {}
    async for sdk_msg in client.receive_response():
        if isinstance(sdk_msg, ResultMessage):
            last_result = sdk_msg
        for event in translator.feed(sdk_msg):
            await runner.emit(event)
            if isinstance(event, ToolCallStart):
                pending_starts.append(event)
                if event.tool_name == "TodoWrite":
                    await runner.emit(_make_todo_update(event))
            elif isinstance(event, ToolCallEnd):
                pending_ends[event.tool_call_id] = event
    return last_result, pending_starts, pending_ends


def _build_tool_records(
    pending_starts: list[ToolCallStart],
    pending_ends: dict[str, ToolCallEnd],
) -> list[ToolCallRecord]:
    """Pair start/end events into :class:`ToolCallRecord` rows for batch insert."""
    return [
        ToolCallRecord(
            tool_call_id=s.tool_call_id,
            tool_name=s.tool_name,
            input_json=s.tool_input_json,
            output=pending_ends[s.tool_call_id].output_summary
            if s.tool_call_id in pending_ends
            else "",
            ok=pending_ends[s.tool_call_id].ok if s.tool_call_id in pending_ends else None,
            duration_ms=pending_ends[s.tool_call_id].duration_ms
            if s.tool_call_id in pending_ends
            else None,
            error_message=pending_ends[s.tool_call_id].error_message
            if s.tool_call_id in pending_ends
            else None,
        )
        for s in pending_starts
    ]


async def _record_turn_analytics(
    db: Any,
    session: AgentSession,
    last_result: ResultMessage | None,
) -> None:
    """Capture per-turn token usage for the analytics tables (spec §4.1)."""
    _usage = extract_model_usage(
        last_result.model_usage if last_result is not None else None,
        session.config.decision,
    )
    await capture_turn(
        db,
        session_id=session.config.session_id,
        model=session.config.decision.executor_model,
        input_tokens=_usage.executor_input_tokens + _usage.advisor_input_tokens,
        output_tokens=_usage.executor_output_tokens + _usage.advisor_output_tokens,
        cache_read_tokens=_usage.cache_read_tokens,
        cache_creation_tokens=_usage.cache_creation_tokens,
    )


async def _finish_turn(
    runner: SessionRunner,
    session: AgentSession,
    translator: SDKEventTranslator,
    persist_fn: MessagePersistence,
    *,
    last_result: ResultMessage | None,
    pending_starts: list[ToolCallStart],
    pending_ends: dict[str, ToolCallEnd],
    was_stopped: bool,
) -> None:
    """Emit ``TurnStopped`` (feature-2-004) and persist the assistant row."""
    if was_stopped and translator.message_id is not None:
        await runner.emit(
            TurnStopped(
                session_id=session.config.session_id,
                message_id=translator.message_id,
            )
        )
    db = session.config.db
    body = translator.final_body()
    if db is not None and translator.message_id is not None and body:
        msg = await persist_fn(
            db,
            session_id=session.config.session_id,
            content=body,
            decision=session.config.decision,
            model_usage=last_result.model_usage if last_result is not None else None,
            total_cost_usd=last_result.total_cost_usd if last_result is not None else None,
            stopped=was_stopped,
        )
        if pending_starts:
            await tool_calls_db.insert_batch(
                db,
                session_id=session.config.session_id,
                message_id=msg.id,
                records=_build_tool_records(pending_starts, pending_ends),
            )
    if db is not None:
        await _record_turn_analytics(db, session, last_result)


async def _do_run_one_turn(
    runner: SessionRunner,
    session: AgentSession,
    client: ClaudeSDKClient,
    translator: SDKEventTranslator,
    persist_fn: MessagePersistence,
    prompt: QueuedPrompt,
) -> None:
    """Inner body of a turn (extracted so the stop_watcher wrapper stays clean)."""
    translator.begin_turn()
    runner.set_status(
        RunnerStatus(
            is_running=True,
            is_awaiting_user=False,
            routing_decision=session.config.decision,
        )
    )
    await runner.emit(
        UserMessage(
            session_id=session.config.session_id,
            message_id=prompt.message_id,
            content=prompt.content,
        )
    )
    query_content = prompt.content
    if prompt.force_advisor and session.config.decision.advisor_model is not None:
        query_content = FORCE_ADVISOR_INSTRUCTION + prompt.content
    sdk_uuid = bearings_to_sdk_uuid(session.config.session_id)
    await client.query(query_content, session_id=sdk_uuid)
    last_result, pending_starts, pending_ends = await _collect_turn_events(
        runner, client, translator
    )
    # Auth errors sometimes arrive as message content (AssistantMessage.error ==
    # "authentication_failed") rather than as Python exceptions.  Detect both
    # paths here and raise so run_session_loop's credential-reload retry fires
    # instead of persisting the error text as a regular chat message.
    auth_error_text = translator.turn_auth_error
    if auth_error_text is None and last_result is not None and is_auth_result(last_result):
        auth_error_text = last_result.result or "Invalid authentication credentials"
    if auth_error_text is not None:
        raise RuntimeError(f"Invalid authentication credentials: {auth_error_text}")
    was_stopped = runner.stop_event.is_set()
    await _finish_turn(
        runner,
        session,
        translator,
        persist_fn,
        last_result=last_result,
        pending_starts=pending_starts,
        pending_ends=pending_ends,
        was_stopped=was_stopped,
    )
