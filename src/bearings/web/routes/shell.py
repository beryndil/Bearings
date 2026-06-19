"""Shell routes — ``POST /api/shell/exec`` (blocking) and
``POST /api/shell/open`` (fire-and-forget, M-12/R-4).

Per ``docs/architecture-v1.md`` §1.1.5 ``web/routes/shell.py``
dispatches argv via :func:`bearings.agent.shell.run_argv` —
``subprocess.run`` with ``shell=False``, allowlist gate on argv[0],
bounded timeout. tool-output-streaming.md does NOT cover this user-
side surface (that doc is the agent-tool side); see
``src/bearings/config/constants.py`` §"Shell exec" for the
decided-and-documented contract.

``POST /api/shell/open`` provides fire-and-forget spawn semantics for
GUI applications (editors, file managers) that must not block the HTTP
response.  It returns 204 immediately after verifying the argv passes
the allowlist; it does not wait for the child to exit.

Security stance documented at the agent-helper level. The route
maps :class:`ShellValidationError` to the relevant 4xx and surfaces
:data:`ShellExitReason.TIMEOUT` as 504.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from bearings.agent.shell import (
    ShellExitReason,
    ShellValidationError,
    open_argv,
    run_argv,
)
from bearings.config.settings import ShellCfg
from bearings.web.models.shell import ShellExecIn, ShellExecOut

router = APIRouter()


def _cfg(request: Request) -> ShellCfg:
    """Pull the :class:`ShellCfg` off ``app.state``; falls back to defaults."""
    cfg = getattr(request.app.state, "shell_cfg", None)
    if cfg is None:
        return ShellCfg()
    if not isinstance(cfg, ShellCfg):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="shell_cfg on app.state is not a ShellCfg instance",
        )
    return cfg


@router.post("/api/shell/exec", response_model=ShellExecOut, operation_id="shell-exec")
async def post_exec(payload: ShellExecIn, request: Request) -> ShellExecOut:
    """Validate + dispatch ``payload.argv`` against the configured allowlist."""
    cfg = _cfg(request)
    try:
        result = run_argv(
            payload.argv,
            allowed=cfg.allowed_commands,
            timeout_s=cfg.timeout_s,
            output_max_bytes=cfg.output_max_bytes,
        )
    except ShellValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if result.reason is ShellExitReason.TIMEOUT:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(f"argv {payload.argv[0]!r} exceeded {cfg.timeout_s}s timeout"),
        )
    return ShellExecOut(
        exit_code=result.exit_code,
        reason=result.reason.value,
        stdout=result.stdout,
        stderr=result.stderr,
        duration_s=result.duration_s,
    )


@router.post(
    "/api/shell/open",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="shell-open",
    summary="Fire-and-forget GUI spawn",
    description=(
        "Spawn ``argv`` detached from the server process "
        "(``start_new_session=True``) and return 204 immediately. "
        "Designed for GUI targets (editors, file managers) that must "
        "not block the HTTP response. Returns 400 when the allowlist is "
        "empty (shell not configured), 422 when the argv is invalid."
    ),
)
async def post_open(payload: ShellExecIn, request: Request) -> None:
    """Validate ``payload.argv`` then spawn detached; returns 204 immediately."""
    cfg = _cfg(request)
    if not cfg.allowed_commands:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="shell not configured — allowed_commands is empty",
        )
    try:
        open_argv(payload.argv, allowed=cfg.allowed_commands)
    except ShellValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"could not spawn process: {exc}",
        ) from exc


__all__ = ["router"]
