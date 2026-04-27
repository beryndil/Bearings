"""WebSocket handler for agent sessions.

This is now a thin subscriber on top of `SessionRunner`. The runner
owns the `AgentSession`, the stream loop, and event persistence; the
handler just forwards incoming control frames (`prompt`, `stop`,
`set_permission_mode`) and pushes outbound events to the socket.

Disconnect no longer stops the agent — the runner keeps going, and a
reconnect (optionally with `?since_seq=N`) replays any buffered events
that arrived while the client was away. That's what makes sessions
independent: you can walk away from a question mid-stream, do work in
another session, and come back to the finished result.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import orjson
from claude_agent_sdk import ThinkingConfig
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from bearings import metrics
from bearings.agent.runner import SessionRunner, _Envelope
from bearings.agent.session import AgentSession
from bearings.api.auth import check_ws_auth, check_ws_origin, ws_accept_subprotocol
from bearings.config import ThinkingMode
from bearings.db import store

log = logging.getLogger(__name__)


def _thinking_config(mode: ThinkingMode | None) -> ThinkingConfig | None:
    """Translate the `agent.thinking` config knob into the SDK's
    ThinkingConfig TypedDict. Kept in the session wiring layer so the
    SDK type stays an implementation detail of ws_agent."""
    if mode == "adaptive":
        return {"type": "adaptive"}
    if mode == "disabled":
        return {"type": "disabled"}
    return None


router = APIRouter(tags=["agent-ws"])

CODE_UNAUTHORIZED = 4401
CODE_SESSION_NOT_FOUND = 4404
# 2026-04-21 security audit §1: rejects cross-origin attachment so a
# malicious tab in the same browser can't drive the agent. Paired with
# `check_ws_origin` in `bearings.api.auth`.
CODE_FORBIDDEN_ORIGIN = 4403
# v0.4.0: a client tried to attach the agent loop to a non-chat
# session. Originally every non-chat kind (checklist, etc.) rejected
# here; v0.5.2 opened checklist sessions to the agent loop so the
# ChecklistView can host an embedded chat about the whole list. This
# code stays in the protocol for future session kinds that genuinely
# can't run an agent. 4400 = generic bad protocol input; paired with an
# explicit `reason` string.
CODE_SESSION_KIND_UNSUPPORTED = 4400

# Session kinds that can spawn an agent runner. Checklist sessions
# joined this set in v0.5.2 — the prompt assembler injects a
# `checklist_overview` layer so the agent sees the list's structure on
# every turn, and the ChecklistView frontend renders a compact chat
# panel above the list body.
RUNNABLE_KINDS = {"chat", "checklist"}


async def _resolve_session_for_runner(conn: Any, session_id: str) -> dict[str, Any]:
    """Fetch the session row and re-check that the kind can spawn a
    runner. Defense in depth: the WS handler already rejects unrunnable
    session kinds before reaching the factory, but if a future caller
    (imports, migrations, tests) skips that gate, fail loudly here
    rather than spawning an SDK subprocess that has nothing to do."""
    row = await store.get_session(conn, session_id)
    assert row is not None, "caller must verify the session exists first"
    if row.get("kind", "chat") not in RUNNABLE_KINDS:
        raise ValueError(
            f"cannot build runner for session kind={row.get('kind')!r}; "
            f"runnable kinds: {sorted(RUNNABLE_KINDS)!r}"
        )
    return row


def _build_agent_session(
    session_id: str,
    row: dict[str, Any],
    agent_cfg: Any,
    conn: Any,
) -> AgentSession:
    """Translate a DB row + agent config into an AgentSession.

    Restores `permission_mode` from the DB (migration 0012) so a
    browser reload doesn't silently roll a user back to 'default';
    NULL in the DB falls back to the profile's
    `default_permission_mode`. Wires the permission-profile gates
    from the 2026-04-21 security audit §5 (setting_sources +
    inherit_*) and the token-cost plan Waves 2–3 switches from
    `enumerated-inventing-ullman.md` (tool_output_cap_chars,
    enable_*) — `AgentCfg` defaults reproduce the recommended
    shipping state. `setting_sources` is snapshotted to a fresh
    list so a per-session mutation can't leak into config."""
    permission_mode = row.get("permission_mode") or agent_cfg.default_permission_mode
    return AgentSession(
        session_id,
        row["working_dir"],
        row["model"],
        max_budget_usd=row.get("max_budget_usd"),
        db=conn,
        sdk_session_id=row.get("sdk_session_id"),
        permission_mode=permission_mode,
        thinking=_thinking_config(agent_cfg.thinking),
        setting_sources=list(agent_cfg.setting_sources)
        if agent_cfg.setting_sources is not None
        else None,
        inherit_mcp_servers=agent_cfg.inherit_mcp_servers,
        inherit_hooks=agent_cfg.inherit_hooks,
        tool_output_cap_chars=agent_cfg.tool_output_cap_chars,
        enable_bearings_mcp=agent_cfg.enable_bearings_mcp,
        enable_precompact_steering=agent_cfg.enable_precompact_steering,
        enable_researcher_subagent=agent_cfg.enable_researcher_subagent,
    )


def _make_prompt_dispatcher(app: Any) -> Any:
    """Build the cross-runner prompt dispatcher (audit item #519).

    Closure over `app` so the lockout-deny callback path can lazy-spawn
    the orchestrator's runner via the registry — same in-process route
    `POST /api/sessions/{id}/prompt` takes, just without the HTTP hop.
    Defined here (not on the runner) so the runner module never
    imports `api.*` and the agent → api circular stays broken."""

    async def _dispatch_prompt(target_id: str, content: str) -> None:
        registry = app.state.runners
        target_runner = await registry.get_or_create(
            target_id, factory=lambda sid: build_runner(app, sid)
        )
        await target_runner.submit_prompt(content)

    return _dispatch_prompt


async def build_runner(app: Any, session_id: str) -> SessionRunner:
    """Construct a SessionRunner wired to app-scoped state.

    Used as the factory passed into `RunnerRegistry.get_or_create`
    (`bearings.agent.registry`) — keeps all the FastAPI-specific
    wiring out of the runner module. Public (was `_build_runner`
    until v0.21.0) because the prompt-injection HTTP route
    (`POST /api/sessions/{id}/prompt`) needs the same factory to
    lazily spawn a runner when an external caller dispatches into a
    session that hasn't been opened in a tab yet."""
    conn = app.state.db
    row = await _resolve_session_for_runner(conn, session_id)
    agent = _build_agent_session(session_id, row, app.state.settings.agent, conn)
    runner = SessionRunner(
        session_id,
        agent,
        conn,
        # Pull the broker off app.state so runner publishes reach every
        # `/ws/sessions` subscriber. Absent on tests that skip the full
        # app wiring — `getattr` keeps the factory usable there.
        sessions_broker=getattr(app.state, "sessions_broker", None),
        # Phase-1 File Display: auto-register hook in turn_executor
        # reads `serve_roots` + `max_register_size_mb` off this. Pulled
        # off settings (not snapshotted) so a config edit + reload
        # picks up new roots on the next runner construction.
        artifacts_cfg=app.state.settings.artifacts,
        prompt_dispatch=_make_prompt_dispatcher(app),
    )
    # Late-bind the approval callback: the SDK's `can_use_tool` hook
    # parks futures on the runner, but the runner only exists after
    # the agent is constructed. Binding here keeps the agent ignorant
    # of the runner (circular import otherwise) while giving the SDK
    # a real coroutine to call when a gated tool wants permission.
    agent.can_use_tool = runner.can_use_tool
    return runner


def _parse_since_seq(websocket: WebSocket) -> int:
    """Read the client's replay cursor from the query string. Clients
    track the last seq they've rendered per session; on reconnect they
    pass it so the runner replays only events newer than that. Missing
    or malformed values fall back to 0 (replay whatever's in the
    buffer) — the frontend dedupes completed messages by id, so
    double-replay is harmless."""
    raw = websocket.query_params.get("since_seq")
    if raw is None:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


async def _send_frame(websocket: WebSocket, frame: dict[str, Any]) -> None:
    """Serialize `frame` with orjson and push it as a text frame.

    Used for ad-hoc frames the runner ring buffer doesn't own (the
    `runner_status` snapshot emitted on connect). Hot-path envelope
    sends bypass this helper and use the pre-encoded `env.wire` string
    built in `_Envelope.__init__`, which saves one `orjson.dumps(...)
    .decode()` per subscriber per event. Starlette's stock `send_json`
    routes through the stdlib `json` encoder, which dominates CPU on
    event-heavy turns; orjson is ~2-3x faster on the dict/str/int
    payloads we send. We decode to str because the frontend contract
    is text frames — switching to `send_bytes` would flip the opcode
    and break the client."""
    await websocket.send_text(orjson.dumps(frame).decode())


# Idle ping cadence. When no envelope arrives for this long, the
# forwarder emits a `{type:"ping"}` frame. Two jobs: (1) surface TCP
# corpse sockets that `WebSocketDisconnect` missed — a dead half-open
# connection accepts a few queued writes before the kernel raises, so
# a failed send here breaks us out of the subscription and the finally
# block cleans up. (2) Complement `tool_progress`: progress ticks only
# fire while a tool call is live, so a completely idle session (no
# running turn, no tool work) would otherwise hold the socket silent
# forever. 15s is chosen to be well under the 60s Nginx default
# `proxy_read_timeout` so a reverse-proxy deployment won't drop the
# socket mid-idle; anyone fronting Bearings with a stricter proxy can
# still lose the socket but at least the diagnostic will appear in
# server logs rather than as a "why did my tab die" mystery.
WS_IDLE_PING_INTERVAL_S = 15.0


async def _forward_events(websocket: WebSocket, queue: asyncio.Queue[_Envelope]) -> None:
    """Pull envelopes off the runner's subscriber queue and write them
    to the socket. Each frame carries `_seq` so the client can advance
    its replay cursor. The envelope arrives with its wire form already
    encoded (see `_Envelope.__init__`), so the fan-out cost is a single
    `send_text` per subscriber — no per-send JSON serialization. Exits
    on send failure (disconnect).

    On idle (no envelope for `WS_IDLE_PING_INTERVAL_S`), emits a ping
    frame — see the constant's docstring for the two jobs it does.
    Pings carry no `_seq` (not in the ring buffer, not persisted) so a
    reconnecting client's replay cursor stays on real events only; the
    frontend reducer's `_seq` guard reads `typeof event._seq ===
    'number'` and skips the bump when absent."""
    while True:
        try:
            env = await asyncio.wait_for(queue.get(), timeout=WS_IDLE_PING_INTERVAL_S)
        except TimeoutError:
            try:
                # `ts` is server wall-clock in ms. Frontend doesn't need
                # it for anything structural — the reducer skips unknown
                # types — but logging / debugging a latency issue is
                # easier with a timestamp already on the frame.
                await websocket.send_text(
                    orjson.dumps({"type": "ping", "ts": int(time.time() * 1000)}).decode()
                )
            except (WebSocketDisconnect, RuntimeError):
                return
            continue
        try:
            await websocket.send_text(env.wire)
        except (WebSocketDisconnect, RuntimeError):
            # Socket died under us — normal at navigation. The outer
            # handler's finally block will clean up the subscription.
            return


async def _accept_and_validate_session(
    websocket: WebSocket, session_id: str
) -> dict[str, Any] | None:
    """Run the connection-handshake gates and resolve the session row.

    Echoes the bearer-subprotocol marker when the client offered it so
    browsers can deliver the token off-URL. Origin check runs before
    auth so a cross-origin attacker can't probe the auth error to
    distinguish configured-vs-unconfigured servers. Returns the session
    row on success; closes the socket with the appropriate code and
    returns `None` on any reject."""
    await websocket.accept(subprotocol=ws_accept_subprotocol(websocket))
    if not check_ws_origin(websocket):
        await websocket.close(code=CODE_FORBIDDEN_ORIGIN, reason="origin not allowed")
        return None
    if not check_ws_auth(websocket):
        await websocket.close(code=CODE_UNAUTHORIZED)
        return None
    row = await store.get_session(websocket.app.state.db, session_id)
    if row is None:
        await websocket.close(code=CODE_SESSION_NOT_FOUND)
        return None
    if row.get("kind", "chat") not in RUNNABLE_KINDS:
        # Future non-runnable kinds land here. Close loud so the bug
        # is obvious if a frontend ever tries to connect to a kind
        # whose UI should be local-only.
        await websocket.close(
            code=CODE_SESSION_KIND_UNSUPPORTED,
            reason="session kind does not support agent attachment",
        )
        return None
    return row


async def _send_initial_runner_status(
    websocket: WebSocket, runner: SessionRunner, session_id: str
) -> bool:
    """Push the ground-truth runner-status snapshot as the first frame.

    After a server restart the new runner's ring buffer is empty, so a
    client that disconnected mid-turn never receives a
    `message_complete` — `streamingActive` would stay true forever.
    This frame lets the client reconcile: if it thought a turn was
    live but the runner is idle, it's safe to clear the streaming
    fringe and refresh from DB. Returns False if the socket died
    mid-send so the caller can short-circuit to cleanup."""
    try:
        await _send_frame(
            websocket,
            {
                "type": "runner_status",
                "session_id": session_id,
                "is_running": runner.is_running,
                "is_awaiting_user": runner.is_awaiting_user,
            },
        )
    except (WebSocketDisconnect, RuntimeError):
        return False
    return True


async def _replay_buffered_events(websocket: WebSocket, replay: list[_Envelope]) -> bool:
    """Push each replay envelope's pre-encoded wire form to the socket.

    Sent before live frames so the client sees missed events in order.
    Using `env.wire` skips per-send orjson encode — a reconnecting tab
    doesn't pay N × encode for the replay window. Returns False on
    disconnect so the caller can short-circuit to cleanup."""
    for env in replay:
        try:
            await websocket.send_text(env.wire)
        except (WebSocketDisconnect, RuntimeError):
            return False
    return True


def _parse_prompt_attachments(raw: Any) -> list[dict[str, Any]]:
    """Filter the composer's `[File N]` sidecar payload to well-formed
    entries. The client sends raw dicts — we drop anything missing the
    expected `(n: int, path: str)` pair so a malformed payload can't
    crash the runner. A missing key upstream just means a plain-text
    prompt with no attachments."""
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for entry in raw:
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("n"), int)
            and isinstance(entry.get("path"), str)
        ):
            result.append(
                {
                    "n": entry["n"],
                    "path": entry["path"],
                    "filename": str(entry.get("filename", "")),
                    "size_bytes": int(entry.get("size_bytes", 0)),
                }
            )
    return result


async def _handle_set_permission_mode(
    websocket: WebSocket,
    app: Any,
    runner: SessionRunner,
    session_id: str,
    payload: dict[str, Any],
) -> None:
    """Profile-gated permission-mode flip.

    Refuses `bypassPermissions` escalation when the active config
    disallows it. Today's default (and `power-user`/`workstation`
    profiles) leaves `allow_bypass_permissions=True`, so the refusal
    only bites under the `safe` profile or an operator who opted in.
    Silent ignore + a wire `error` so the UI knows the click did
    nothing instead of appearing to succeed; the event reducer
    surfaces `error` events as a transient toast.

    On the allow branch the call is awaited because the runner also
    retro-applies the new mode to any parked approval (see the
    broker's `resolve_for_mode` matrix) — awaiting ensures any
    `approval_resolved` fan-out lands before the next inbound frame."""
    mode = payload.get("mode")
    allow_bypass = app.state.settings.agent.allow_bypass_permissions
    if mode == "bypassPermissions" and not allow_bypass:
        await _send_frame(
            websocket,
            {
                "type": "error",
                "session_id": session_id,
                "message": ("bypassPermissions disabled by active permission profile"),
            },
        )
        return
    await runner.set_permission_mode(mode or None)


async def _handle_approval_response(runner: SessionRunner, payload: dict[str, Any]) -> None:
    """Resolve a pending `can_use_tool` future.

    Unknown / already-resolved ids are no-ops inside the runner, so two
    tabs racing to answer the same modal is safe. `updated_input` is
    the UI-collected override the SDK will hand to the tool
    (AskUserQuestion answers ride here). Non-dict values are dropped —
    we never want a malformed payload to clobber the tool's actual
    input."""
    request_id = payload.get("request_id")
    decision = payload.get("decision")
    reason = payload.get("reason")
    updated_input = payload.get("updated_input")
    if isinstance(request_id, str) and decision in ("allow", "deny"):
        await runner.resolve_approval(
            request_id,
            decision,
            reason if isinstance(reason, str) else None,
            updated_input if isinstance(updated_input, dict) else None,
        )


async def _dispatch_ws_message(
    websocket: WebSocket,
    app: Any,
    runner: SessionRunner,
    session_id: str,
    payload: dict[str, Any],
) -> None:
    """Route one inbound control frame to the appropriate handler.

    Unknown message types are silently ignored — keeps the protocol
    forward-compatible the same way it was pre-refactor."""
    msg_type = payload.get("type")
    if msg_type == "prompt":
        prompt = str(payload.get("content", ""))
        attachments = _parse_prompt_attachments(payload.get("attachments"))
        await runner.submit_prompt(prompt, attachments=attachments or None)
    elif msg_type == "stop":
        await runner.request_stop()
    elif msg_type == "set_permission_mode":
        await _handle_set_permission_mode(websocket, app, runner, session_id, payload)
    elif msg_type == "approval_response":
        await _handle_approval_response(runner, payload)


async def _run_receive_loop(
    websocket: WebSocket,
    app: Any,
    runner: SessionRunner,
    session_id: str,
    queue: asyncio.Queue[_Envelope],
) -> None:
    """Spawn the outbound forwarder, then drive the inbound control
    loop until disconnect. The forwarder is cancelled on exit so the
    runner's subscriber queue stops receiving fan-out attempts the
    moment the socket dies. WebSocketDisconnect is the normal exit
    path (the runner keeps running — that's the point of this whole
    refactor); other exceptions get logged so a misbehaving message
    handler is visible without taking the whole server down."""
    forwarder = asyncio.create_task(
        _forward_events(websocket, queue), name=f"ws-forward:{session_id}"
    )
    try:
        while True:
            payload = await websocket.receive_json()
            await _dispatch_ws_message(websocket, app, runner, session_id, payload)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("ws %s: unexpected error in receive loop", session_id)
    finally:
        forwarder.cancel()
        try:
            await forwarder
        except (asyncio.CancelledError, Exception):
            pass


@router.websocket("/ws/sessions/{session_id}")
async def agent_ws(websocket: WebSocket, session_id: str) -> None:
    """Top-level subscriber for an agent session.

    Disconnect doesn't stop the agent — the runner keeps going, and a
    reconnect with `?since_seq=N` replays anything that arrived while
    the client was away. Orchestrates the handshake, subscription,
    initial state snapshot, replay window, and the inbound/outbound
    loops; helpers carry the per-block detail."""
    row = await _accept_and_validate_session(websocket, session_id)
    if row is None:
        return
    app = websocket.app
    since_seq = _parse_since_seq(websocket)
    runner = await app.state.runners.get_or_create(
        session_id, factory=lambda sid: build_runner(app, sid)
    )
    # Directory Context System (v0.6.1): stamp `history.jsonl` start
    # marker + kick off stale-state revalidation. Idempotent on every
    # reconnect; the runner gates internally so the start marker lands
    # exactly once per runner lifetime.
    await runner.note_directory_context_start()
    queue, replay = await runner.subscribe(since_seq)
    metrics.ws_active_connections.inc()
    app.state.active_ws.add(websocket)
    try:
        if not await _send_initial_runner_status(websocket, runner, session_id):
            return
        if not await _replay_buffered_events(websocket, replay):
            return
        await _run_receive_loop(websocket, app, runner, session_id, queue)
    finally:
        runner.unsubscribe(queue)
        app.state.active_ws.discard(websocket)
        metrics.ws_active_connections.dec()
