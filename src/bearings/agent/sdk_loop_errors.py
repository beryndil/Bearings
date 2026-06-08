# mypy: disable-error-code=explicit-any
"""SDK loop error-state logic, SDK option builders, and shared utilities.

``_enter_error_state`` transitions a session to ERROR and fans out a fatal
:class:`ErrorEvent`.  ``_to_sdk_options`` and its helpers build the
:class:`ClaudeAgentOptions` object from the composed :class:`OptionsKwargs`.
``_make_todo_update`` extracts the todos list from a ``TodoWrite`` event.

401-retry helpers (item 625):
    ``_is_auth_error`` — classifies "Invalid authentication credentials" as
    TRANSIENT so the caller can trigger a single credential-reload + retry.
    ``_reload_sdk_credentials`` — reads ``~/.claude/.credentials.json`` to
    verify the rotated bearer is present and logs the event; the actual
    pick-up happens when the SDK spawns a fresh subprocess on re-entry.

Initialize-timeout retry helpers:
    ``_is_init_timeout_error`` — classifies "Control request timeout:
    initialize" as TRANSIENT so the caller can close the subprocess, wait
    briefly, and retry once.  The SDK raises this when the ``claude`` CLI
    subprocess fails to respond to the streaming-mode initialize handshake
    within 60 s — typically a transient startup slowdown under load or while
    MCP servers are warming up.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Final

import aiosqlite
from claude_agent_sdk import ClaudeAgentOptions

from bearings.agent.events import ErrorEvent, TodoWriteUpdate
from bearings.agent.options import OptionsKwargs
from bearings.agent.runner import RunnerStatus, SessionRunner
from bearings.agent.session import AgentSession, SessionStateError
from bearings.db import sessions as sessions_db

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 401 auth-retry helpers (item 625 — token-rotation fix)
# ---------------------------------------------------------------------------

# The exact string the Claude SDK embeds when the bearer token is rejected.
_AUTH_ERROR_MARKER: Final[str] = "Invalid authentication credentials"

# ---------------------------------------------------------------------------
# Initialize-timeout retry helpers
# ---------------------------------------------------------------------------

# The exact string raised by the SDK when the streaming-mode initialize
# handshake with the CLI subprocess does not complete within 60 s.
# Source: claude_agent_sdk/_internal/query.py _send_control_request().
_INIT_TIMEOUT_MARKER: Final[str] = "Control request timeout: initialize"


def _is_init_timeout_error(exc: BaseException) -> bool:
    """Return ``True`` when *exc* is a transient initialize-handshake timeout.

    The SDK raises ``"Control request timeout: initialize"`` when
    ``anyio.fail_after(60.0)`` fires during the streaming-mode initialize
    exchange.  This is a subprocess-startup transient — the next subprocess
    spawn usually succeeds once system load subsides.
    """
    return _INIT_TIMEOUT_MARKER in str(exc)


# Path to the Claude Max OAuth credentials file.
_CREDENTIALS_PATH: Final[Path] = Path.home() / ".claude" / ".credentials.json"


class TokenExpiredError(RuntimeError):
    """Raised when the OAuth token in the credentials file is already expired.

    Distinct from a transient rotation 401 (where a fresh token is already in
    the file).  Signals that re-authentication is required — the retry loop
    must not attempt a subprocess spawn with the known-stale bearer.
    """


def _is_auth_error(exc: BaseException) -> bool:
    """Return ``True`` when *exc* carries the 401 auth-credentials marker.

    The marker is ``"Invalid authentication credentials"`` — the exact
    string the Claude SDK inserts into the exception message when it
    receives an HTTP 401 from the API.  Matching by substring is
    intentionally broad to survive minor SDK wording changes.
    """
    return _AUTH_ERROR_MARKER in str(exc)


def _reload_sdk_credentials() -> None:
    """Log a 401 credential-reload event and verify the credentials file.

    The SDK subprocess reads ``~/.claude/.credentials.json`` on startup.
    Closing the current client context and re-opening it (which spawns a
    new subprocess) picks up the rotated bearer automatically.  This
    function verifies the file is readable, logs whether an
    ``accessToken`` is present, and records the event for diagnostics.

    Raises:
        TokenExpiredError: When the ``expiresAt`` field in the credentials
            file is in the past.  A mid-rotation 401 means Anthropic has
            already issued a fresh bearer that the retry subprocess will pick
            up; an *expired* token means the user needs to re-authenticate
            (``claude`` CLI) before any subprocess attempt can succeed.
            Raising here prevents a guaranteed-to-fail second 401 and
            surfaces an actionable message instead.

    Failures to read or parse the credentials file are logged as warnings —
    the retry proceeds regardless so the next subprocess attempt surfaces a
    clearer error.
    """
    try:
        data = json.loads(_CREDENTIALS_PATH.read_text(encoding="utf-8"))
        oauth = data.get("claudeAiOauth", {})
        has_token = bool(oauth.get("accessToken"))
        expires_at_ms: int = int(oauth.get("expiresAt") or 0)
        now_ms = int(time.time() * 1000)
        token_expired = expires_at_ms > 0 and expires_at_ms <= now_ms
        _log.info(
            "401 auth error: credential reload from %s "
            "(accessToken present=%s, token_expired=%s) — recreating SDK subprocess",
            _CREDENTIALS_PATH,
            has_token,
            token_expired,
        )
        if token_expired:
            import datetime

            expires_iso = datetime.datetime.fromtimestamp(
                expires_at_ms / 1000, tz=datetime.UTC
            ).isoformat()
            raise TokenExpiredError(
                f"OAuth token expired at {expires_iso}. "
                "Re-authenticate by running 'claude' in a terminal."
            )
    except TokenExpiredError:
        raise
    except Exception as read_exc:
        _log.warning(
            "401 auth error: failed to read credentials at %s: %s — retrying SDK subprocess anyway",
            _CREDENTIALS_PATH,
            read_exc,
        )


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
