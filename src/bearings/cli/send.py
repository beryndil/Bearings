# mypy: disable-error-code=explicit-any
"""``bearings send`` subcommand — one-shot prompt dispatch with streaming.

Per ``docs/behavior/bearings-cli.md`` §"bearings send":

* POSTs a prompt to ``POST /api/sessions/{id}/prompt`` via HTTP.
* Connects to the per-session WebSocket stream at
  ``/ws/sessions/{id}`` and streams JSON event frames to stdout.
* ``--format json`` (default): one JSON object per line in arrival order,
  ending with a ``message_complete`` or ``error`` frame.
* ``--format pretty``: tokens stream inline; tool calls render as
  ``↳ tool <name> (<input>)`` / ``← ok: <output>``; each turn ends
  with a 40-character horizontal rule and a cost readout when known.
* Exit ``0`` on ``message_complete``, exit ``1`` on ``error``.
* Auth: ``--token`` overrides config; otherwise ``auth.token`` from config
  when ``auth.enabled``.  With auth disabled, no token is sent.

Per arch §1.1.1 the handler body stays thin — one call into
:func:`_run_send`.

Pydantic / Any carve-out
------------------------
``json.loads()`` returns ``Any``; the frame-parsing helpers below annotate
the locals accordingly.  The ``# mypy: disable-error-code=explicit-any``
at module level is the narrow carve-out — every public function retains
its explicit typed signature.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.error
import urllib.request
from typing import Any

from bearings.config.constants import (
    CLI_EXIT_OK,
    CLI_EXIT_OPERATION_FAILURE,
    DEFAULT_HOST,
    DEFAULT_PORT,
    SEND_DEFAULT_FORMAT,
    SEND_EVENT_TYPE_ERROR,
    SEND_EVENT_TYPE_MESSAGE_COMPLETE,
    SEND_EVENT_TYPE_TOKEN,
    SEND_EVENT_TYPE_TOOL_RESULT,
    SEND_EVENT_TYPE_TOOL_START,
    SEND_PRETTY_RULE_WIDTH,
    SEND_PROMPT_PATH_TEMPLATE,
    SEND_WS_FRAME_KIND_EVENT,
    SEND_WS_PATH_TEMPLATE,
)


def build_subparser(
    parent: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Wire the ``send`` subcommand into ``parent``."""
    p = parent.add_parser(
        "send",
        help="send a one-shot prompt to a session and stream events",
        description=(
            "POST a prompt to an existing Bearings session and stream the "
            "agent's response events to stdout. Connects to the per-session "
            "WebSocket at /ws/sessions/{id} for streaming."
        ),
    )
    p.add_argument(
        "--session",
        required=True,
        metavar="ID",
        help="session id to send the prompt to (required)",
    )
    p.add_argument(
        "--host",
        default=None,
        help=f"server host (default: {DEFAULT_HOST})",
    )
    p.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"server port (default: {DEFAULT_PORT})",
    )
    p.add_argument(
        "--token",
        default=None,
        metavar="T",
        help="auth token; overrides auth.token from config",
    )
    p.add_argument(
        "--format",
        dest="format_",
        choices=("json", "pretty"),
        default=SEND_DEFAULT_FORMAT,
        metavar="FORMAT",
        help="output format: json (default) or pretty",
    )
    p.add_argument(
        "message",
        help="prompt text to send to the session",
    )
    p.set_defaults(func=_cmd_send)


def _cmd_send(args: argparse.Namespace) -> int:
    """Handler for ``bearings send``.

    Resolves host/port from args or config, then delegates all I/O to
    :func:`_run_send` via :func:`asyncio.run`.
    """
    from bearings.config.settings import Settings

    settings = Settings()
    host: str = args.host if args.host is not None else settings.host
    port: int = args.port if args.port is not None else settings.port

    # Token resolution: --token > config (when auth enabled) > None.
    token: str | None = args.token
    if token is None:
        try:
            auth_cfg = getattr(settings, "auth", None)
            if auth_cfg is not None and getattr(auth_cfg, "enabled", False):
                token = getattr(auth_cfg, "token", None)
        except Exception:
            pass

    return asyncio.run(
        _run_send(
            session_id=args.session,
            host=host,
            port=port,
            token=token,
            message=args.message,
            format_=args.format_,
        )
    )


# ---------------------------------------------------------------------------
# Async domain logic
# ---------------------------------------------------------------------------


async def _run_send(
    *,
    session_id: str,
    host: str,
    port: int,
    token: str | None,
    message: str,
    format_: str,
) -> int:
    """Post *message* to *session_id* and stream the agent response.

    Opens the WebSocket **before** POSTing the prompt to avoid a race where
    events arrive before the client is subscribed.  Returns the CLI exit code
    (``0`` on ``message_complete``, ``1`` on ``error`` or connection failure).
    """
    from websockets.asyncio.client import connect as ws_connect

    base_url = f"http://{host}:{port}"
    ws_base = f"ws://{host}:{port}"
    prompt_url = base_url + SEND_PROMPT_PATH_TEMPLATE.format(session_id=session_id)
    ws_url = ws_base + SEND_WS_PATH_TEMPLATE.format(session_id=session_id)

    try:
        async with ws_connect(ws_url) as ws:
            # POST the prompt inside the WS context so events are captured.
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None,
                    lambda: _http_post_prompt(prompt_url, message, token),
                )
            except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
                sys.stderr.write(f"bearings send: failed to post prompt: {exc}\n")
                return CLI_EXIT_OPERATION_FAILURE

            # Stream events from the WebSocket.
            async for raw_msg in ws:
                result = _process_ws_frame(raw_msg, format_)
                if result is not None:
                    return result

    except (ConnectionRefusedError, OSError) as exc:
        sys.stderr.write(f"bearings send: cannot connect to {ws_url}: {exc}\n")
        return CLI_EXIT_OPERATION_FAILURE
    except Exception as exc:
        sys.stderr.write(f"bearings send: stream error: {exc}\n")
        return CLI_EXIT_OPERATION_FAILURE

    # WS closed without a terminal event.
    sys.stderr.write("bearings send: stream closed without message_complete\n")
    return CLI_EXIT_OPERATION_FAILURE


def _process_ws_frame(raw_msg: str | bytes, format_: str) -> int | None:
    """Decode one WebSocket frame and return a CLI exit code or ``None`` to continue.

    Returns :data:`CLI_EXIT_OK` on ``message_complete``,
    :data:`CLI_EXIT_OPERATION_FAILURE` on ``error``, and ``None`` for
    heartbeats, non-event frames, or frames that cannot be decoded.
    """
    if not isinstance(raw_msg, str):
        return None
    try:
        frame: dict[str, Any] = json.loads(raw_msg)
    except (json.JSONDecodeError, ValueError):
        return None
    if frame.get("kind") != SEND_WS_FRAME_KIND_EVENT:
        return None  # heartbeat — ignore
    raw_event = frame.get("event", {})
    if not isinstance(raw_event, dict):
        return None
    event: dict[str, Any] = raw_event
    _print_event(event, format_)
    event_type = event.get("type")
    if event_type == SEND_EVENT_TYPE_MESSAGE_COMPLETE:
        return CLI_EXIT_OK
    if event_type == SEND_EVENT_TYPE_ERROR:
        return CLI_EXIT_OPERATION_FAILURE
    return None


def _http_post_prompt(url: str, message: str, token: str | None) -> None:
    """POST *message* as a JSON prompt to *url* (synchronous, runs in executor).

    Raises :exc:`urllib.error.URLError` / :exc:`urllib.error.HTTPError` on
    network or server errors — the caller converts these to a CLI error.
    """
    data = json.dumps({"content": message}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as _resp:
        pass  # 202 expected; body is not consumed


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _print_event(event: dict[str, Any], format_: str) -> None:
    """Write one event to stdout in the requested *format_*."""
    if format_ == "json":
        sys.stdout.write(json.dumps(event) + "\n")
        sys.stdout.flush()
    else:
        _print_event_pretty(event)


def _print_event_pretty(event: dict[str, Any]) -> None:
    """Render one event in the human-readable pretty format.

    Per behavior doc §"bearings send":
    * Tokens stream inline without per-frame newlines.
    * Tool calls render as ``↳ tool <name> (<input>)``
      and ``← ok: <output>`` (or ``← error: <body>``).
    * Each ``message_complete`` turn ends with a 40-char horizontal rule
      and a cost readout when known.
    """
    event_type = event.get("type")
    if event_type == SEND_EVENT_TYPE_TOKEN:
        text = event.get("text", "")
        sys.stdout.write(str(text))
        sys.stdout.flush()
    elif event_type == SEND_EVENT_TYPE_TOOL_START:
        name = event.get("name", "unknown")
        input_data = event.get("input", "")
        sys.stdout.write(f"\n↳ tool {name} ({input_data})\n")
        sys.stdout.flush()
    elif event_type == SEND_EVENT_TYPE_TOOL_RESULT:
        is_error = event.get("is_error", False)
        content = event.get("content", "")
        prefix = "← error" if is_error else "← ok"
        sys.stdout.write(f"{prefix}: {content}\n")
        sys.stdout.flush()
    elif event_type == SEND_EVENT_TYPE_MESSAGE_COMPLETE:
        # Horizontal rule + optional cost readout.
        rule = "─" * SEND_PRETTY_RULE_WIDTH
        sys.stdout.write(f"\n{rule}\n")
        cost_usd = event.get("cost_usd")
        if cost_usd is not None:
            sys.stdout.write(f"cost: ${float(cost_usd):.4f}\n")
        sys.stdout.flush()


__all__ = ["build_subparser"]
