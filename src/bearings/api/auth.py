"""Bearer-token auth for the REST and WebSocket surfaces.

Opt-in: `auth.enabled = true` + `auth.token = "..."` in config.toml.
Otherwise the server stays open (matches v0.1.0 behavior). Both
`/api/sessions*` and `/api/history*` require the token; `/api/health`
and `/metrics` stay open so ops/monitoring can probe without creds.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, WebSocket, status

# WS bearer-subprotocol marker. The browser `WebSocket` constructor
# can't set an `Authorization` header, so to keep tokens out of the
# URL (access logs, Referer, browser history, process listings) we
# accept them over `Sec-WebSocket-Protocol` instead. Clients pass
# two protocols: the marker below and `bearer.<token>`. The server
# picks the marker in `accept()` so the negotiated protocol never
# echoes the secret. Query-string remains supported for the CLI
# (`bearings send`) but is deprecated for browser clients —
# 2026-04-21 security audit §1 (2026-04-23 fix).
WS_BEARER_SUBPROTOCOL = "bearings.bearer.v1"
_WS_BEARER_PREFIX = "bearer."


def _configured_token(request: Request | WebSocket) -> str | None:
    settings = request.app.state.settings
    if not settings.auth.enabled:
        return None
    token: str | None = settings.auth.token
    if not token:
        # Enabled without a token is a config error; fail closed so
        # nobody thinks auth is on while the server is actually open.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="auth.enabled is true but auth.token is empty",
        )
    return token


def _consteq(a: str, b: str) -> bool:
    """Constant-time string equality. `secrets.compare_digest` raises
    on bytes/str mismatch; we normalize to str upstream so both are
    `str` here. Length differences leak through (compare_digest is
    constant-time over the shorter operand), which is acceptable —
    tokens are fixed-length for a given deploy."""
    return secrets.compare_digest(a, b)


def require_auth(request: Request) -> None:
    expected = _configured_token(request)
    if expected is None:
        return
    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or not _consteq(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _ws_subprotocol_token(websocket: WebSocket) -> str | None:
    """Extract a bearer token from the WS subprotocol handshake.

    Browsers send `Sec-WebSocket-Protocol: bearings.bearer.v1, bearer.<tok>`
    (Starlette exposes the list at `.scope['subprotocols']`). Returns
    the token when both the marker and a `bearer.*` entry are
    present; `None` otherwise — callers fall back to the query-
    string path."""
    protocols: list[str] = list(websocket.scope.get("subprotocols") or [])
    has_marker = WS_BEARER_SUBPROTOCOL in protocols
    if not has_marker:
        return None
    for entry in protocols:
        if entry.startswith(_WS_BEARER_PREFIX):
            return entry[len(_WS_BEARER_PREFIX) :]
    return None


def ws_accept_subprotocol(websocket: WebSocket) -> str | None:
    """Subprotocol to echo on `websocket.accept(subprotocol=...)`.

    When the client offered the bearer marker, we must select it so
    the handshake completes; otherwise return `None` and let the
    server pick nothing (same as today). Never echoes the `bearer.<tok>`
    entry — that would put the secret in the `Sec-WebSocket-Protocol`
    response header."""
    protocols = websocket.scope.get("subprotocols") or []
    if WS_BEARER_SUBPROTOCOL in protocols:
        return WS_BEARER_SUBPROTOCOL
    return None


def check_ws_auth(websocket: WebSocket) -> bool:
    """True if the WS request passes auth. Caller is responsible for
    closing the socket with 4401 on False.

    Two transports are accepted, in order:
      1. `Sec-WebSocket-Protocol: bearings.bearer.v1, bearer.<token>`
         — preferred for browser clients. Keeps the secret out of
         URLs and logs.
      2. `?token=<token>` query string — kept for the CLI (`bearings
         send`) which has no convenient subprotocol plumbing.
    Comparison is constant-time regardless of which path is used.
    """
    settings = websocket.app.state.settings
    if not settings.auth.enabled:
        return True
    expected: str | None = settings.auth.token
    if not expected:
        return False
    presented = _ws_subprotocol_token(websocket)
    if presented is None:
        presented = str(websocket.query_params.get("token", ""))
    return _consteq(presented, expected)


def _allowed_origins(websocket: WebSocket) -> set[str]:
    """Compute the effective allowlist for this request.

    Loopback defaults are derived from `server.port` so a user who
    flips the port doesn't lose their own UI. `server.allowed_origins`
    is merged in to support custom local deployments (Vite dev server,
    reverse proxies). Built per-request rather than cached because
    config changes (admin UI reloads) can change the port without a
    server restart.
    """
    settings = websocket.app.state.settings
    port = settings.server.port
    origins = {
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        f"http://[::1]:{port}",
    }
    origins.update(settings.server.allowed_origins)
    return origins


def check_ws_origin(websocket: WebSocket) -> bool:
    """True if the WS handshake's `Origin` header is allowlisted.

    Mitigates cross-origin agent hijacking: without this, any tab in
    the same browser (including attacker pages served by another
    localhost process) could open the Bearings WS and drive the agent.
    Browsers always send `Origin` on WebSocket upgrades, so a missing
    header fails closed — non-browser clients that need access can set
    `Origin` explicitly to a value in `server.allowed_origins`.

    Caller is responsible for closing the socket with 4403 on False.
    """
    origin = websocket.headers.get("origin")
    if origin is None:
        return False
    return origin in _allowed_origins(websocket)
