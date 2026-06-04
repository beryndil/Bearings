# mypy: disable-error-code=explicit-any
"""SDK loop error-state logic, SDK option builders, and shared utilities.

``_enter_error_state`` transitions a session to ERROR and fans out a fatal
:class:`ErrorEvent`.  ``_to_sdk_options`` and its helpers build the
:class:`ClaudeAgentOptions` object from the composed :class:`OptionsKwargs`.
``_make_todo_update`` extracts the todos list from a ``TodoWrite`` event.

Exec-2B will add 401-retry logic to this module (retry on
``Invalid authentication credentials`` with token refresh).
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

import aiosqlite
from claude_agent_sdk import ClaudeAgentOptions

from bearings.agent.events import ErrorEvent, TodoWriteUpdate
from bearings.agent.options import OptionsKwargs
from bearings.agent.runner import RunnerStatus, SessionRunner
from bearings.agent.session import AgentSession, SessionStateError
from bearings.db import sessions as sessions_db

_log = logging.getLogger(__name__)


async def _enter_error_state(
    runner: SessionRunner,
    session: AgentSession,
    exc: BaseException,
) -> None:
    """Transition the session to ERROR + fan out a fatal ErrorEvent.

    Defensive against the session already being in a terminal state
    (e.g. close() raced with a fatal SDK error) — silently absorbs
    SessionStateError so we still emit the wire frame for any live subscriber.

    Also writes ``error_pending = True`` to the DB so the sidebar error
    indicator survives page reloads (the in-memory ``mark_error`` alone is
    not durable across reconnects).
    """
    _log.warning(
        "session %s: agent loop fatal — %s: %s",
        session.config.session_id,
        type(exc).__name__,
        exc,
        exc_info=exc,
    )
    with contextlib.suppress(SessionStateError):
        await session.mark_error(str(exc))
    # Persist error_pending = True to DB so the red dot survives page reload.
    # Use the session's own DB connection; suppress failures so DB hiccups
    # never shadow the real error.
    db: aiosqlite.Connection | None = getattr(session.config, "db", None)
    if db is not None:
        with contextlib.suppress(Exception):
            await sessions_db.set_error_pending(db, session.config.session_id, True)
    await runner.emit(
        ErrorEvent(
            session_id=session.config.session_id,
            message=f"agent loop error: {exc}",
            fatal=True,
        )
    )
    runner.set_status(
        RunnerStatus(
            is_running=False,
            is_awaiting_user=False,
            routing_decision=session.config.decision,
            is_error=True,
        )
    )


def _make_todo_update(event: Any) -> TodoWriteUpdate:
    """Extract the todos list from a TodoWrite ToolCallStart and wrap it.

    The TodoWrite tool input is ``{"todos": [{id, content, status,
    priority}, ...]}``.  Malformed JSON is treated as an empty list.
    """
    try:
        parsed = json.loads(event.tool_input_json)
        todos = parsed.get("todos", [])
        todos_json = json.dumps(todos)
    except (json.JSONDecodeError, AttributeError):
        todos_json = "[]"
    return TodoWriteUpdate(
        session_id=event.session_id,
        todos_json=todos_json,
    )


def _add_replay_sdk_fields(sdk_kwargs: dict[str, Any], kwargs: OptionsKwargs) -> None:
    """Append SDK history-replay wiring fields to ``sdk_kwargs`` in place.

    Lands the model-swap context-loss fix (2026-05-05).
    """
    if kwargs.session_store is not None:
        sdk_kwargs["session_store"] = kwargs.session_store
    if kwargs.sdk_session_id is not None:
        sdk_kwargs["session_id"] = kwargs.sdk_session_id
    if kwargs.resume is not None:
        sdk_kwargs["resume"] = kwargs.resume


def _add_optional_sdk_fields(sdk_kwargs: dict[str, Any], kwargs: OptionsKwargs) -> None:
    """Append conditionally-present SDK options to ``sdk_kwargs`` in place.

    ``fallback_model`` is dropped when it matches ``model`` because the SDK CLI
    rejects identical pairs ("Fallback model cannot be the same as the main
    model").
    """
    if kwargs.fallback_model and kwargs.fallback_model != kwargs.model:
        sdk_kwargs["fallback_model"] = kwargs.fallback_model
    if kwargs.effort is not None:
        sdk_kwargs["effort"] = kwargs.effort
    if kwargs.system_prompt:
        sdk_kwargs["system_prompt"] = kwargs.system_prompt
    if kwargs.cwd:
        sdk_kwargs["cwd"] = kwargs.cwd
    if kwargs.permission_mode:
        sdk_kwargs["permission_mode"] = kwargs.permission_mode
    if kwargs.setting_sources is not None:
        sdk_kwargs["setting_sources"] = list(kwargs.setting_sources)
    if kwargs.hooks:
        sdk_kwargs["hooks"] = dict(kwargs.hooks)
    _add_replay_sdk_fields(sdk_kwargs, kwargs)


def _to_sdk_options(kwargs: OptionsKwargs) -> ClaudeAgentOptions:
    """Splat :class:`OptionsKwargs` onto :class:`ClaudeAgentOptions`.

    Only SDK-known fields flow through; the routing-shift surplus stays on
    the carrier.  Empty / None safe-defaults are mapped per the SDK shape.
    """
    sdk_kwargs: dict[str, Any] = {
        "model": kwargs.model,
        "betas": list(kwargs.betas),
        "include_partial_messages": kwargs.include_partial_messages,
        "allowed_tools": list(kwargs.allowed_tools),
        "disallowed_tools": list(kwargs.disallowed_tools),
        "mcp_servers": dict(kwargs.mcp_servers),
        "max_budget_usd": kwargs.max_budget_usd,
        "can_use_tool": kwargs.can_use_tool,
    }
    _add_optional_sdk_fields(sdk_kwargs, kwargs)
    return ClaudeAgentOptions(**sdk_kwargs)
