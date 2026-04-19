"""Bearer-token auth for the REST and WebSocket surfaces.

Opt-in: `auth.enabled = true` + `auth.token = "..."` in config.toml.
Otherwise the server stays open (matches v0.1.0 behavior). Both
`/api/sessions*` and `/api/history*` require the token; `/api/health`
and `/metrics` stay open so ops/monitoring can probe without creds.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, WebSocket, status


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


def require_auth(request: Request) -> None:
    expected = _configured_token(request)
    if expected is None:
        return
    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or presented != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def check_ws_auth(websocket: WebSocket) -> bool:
    """True if the WS request passes auth. Caller is responsible for
    closing the socket with 4401 on False."""
    settings = websocket.app.state.settings
    if not settings.auth.enabled:
        return True
    expected: str | None = settings.auth.token
    if not expected:
        return False
    presented = str(websocket.query_params.get("token", ""))
    return presented == expected
