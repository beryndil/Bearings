"""Shell-exec helper — argv-only, allowlisted, bounded.

Per ``docs/architecture-v1.md`` §1.1.5 ``web/routes/shell.py`` is the
user-side dispatch surface (e.g. "open this in the system editor").
This is **not** the agent-side Bash tool — that flows through the SDK
per ``docs/behavior/tool-output-streaming.md``. The behavior docs are
silent on this user-side endpoint; see
``src/bearings/config/constants.py`` §"Shell exec" for the
decided-and-documented contract.

Security stance:

* ``subprocess.run(..., shell=False)`` always.
* argv[0] must be a member of the per-call ``allowed`` frozenset; the
  route layer reads the allowlist from
  :class:`bearings.config.settings.ShellCfg.allowed_commands`.
* Bounded timeout — over-cap calls return :data:`ShellExitReason.TIMEOUT`
  with the spawned process killed first.
* Output streams capped at ``output_max_bytes``; over-cap output is
  truncated tail-style (matching :data:`STREAM_TRUNCATION_MARKER_TEMPLATE`
  shape from the streaming surface).
"""

from __future__ import annotations

import enum
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass

from bearings.config.constants import (
    SHELL_ARGV_ENTRY_MAX_LENGTH,
    SHELL_ARGV_MAX_ENTRIES,
    STREAM_TRUNCATION_MARKER_TEMPLATE,
)


class ShellExitReason(enum.Enum):
    """Terminal status of a :func:`run_argv` call."""

    EXITED = "exited"
    TIMEOUT = "timeout"
    SPAWN_ERROR = "spawn_error"


class ShellValidationError(ValueError):
    """Raised when the validator rejects an argv.

    Carries a ``status_code`` hint the route maps to HTTP status —
    422 for malformed argv / not-allowlisted, 504 for timeouts (which
    surface from :func:`run_argv` not from the validator).
    """

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ShellResult:
    """Outcome of a shell exec."""

    exit_code: int
    reason: ShellExitReason
    stdout: str
    stderr: str
    duration_s: float


def validate_argv(argv: list[str], allowed: Iterable[str]) -> list[str]:
    """Reject malformed / not-allowlisted argv; return the cleaned list.

    Rejection reasons:

    * empty argv (no command).
    * argv length > :data:`SHELL_ARGV_MAX_ENTRIES`.
    * any entry > :data:`SHELL_ARGV_ENTRY_MAX_LENGTH`.
    * argv[0] not in ``allowed`` (the per-call allowlist).
    * argv[0] containing a path separator (``/``) — the allowlist is
      command-name only; a fully qualified path is a different shape.
    """
    if not argv:
        raise ShellValidationError("argv must be non-empty", status_code=422)
    if len(argv) > SHELL_ARGV_MAX_ENTRIES:
        raise ShellValidationError(
            f"argv length {len(argv)} exceeds cap {SHELL_ARGV_MAX_ENTRIES}",
            status_code=422,
        )
    for i, entry in enumerate(argv):
        if not isinstance(entry, str):  # pragma: no cover — Pydantic guards
            raise ShellValidationError(f"argv[{i}] is not a string", status_code=422)
        if len(entry) > SHELL_ARGV_ENTRY_MAX_LENGTH:
            raise ShellValidationError(
                f"argv[{i}] exceeds {SHELL_ARGV_ENTRY_MAX_LENGTH} chars",
                status_code=422,
            )
    head = argv[0]
    if "/" in head:
        raise ShellValidationError(
            f"argv[0] {head!r} must be a bare command name (no path separator)",
            status_code=422,
        )
    allowed_set = frozenset(allowed)
    if head not in allowed_set:
        raise ShellValidationError(
            f"argv[0] {head!r} is not in the shell allowlist",
            status_code=422,
        )
    return list(argv)


def _truncate(text: str, max_bytes: int) -> str:
    """Cap ``text`` at ``max_bytes`` bytes; append truncation marker.

    Operates on the utf-8 byte length; on over-cap the body is
    truncated to ``max_bytes`` bytes (split on a safe boundary), then
    decoded with ``errors="replace"`` so a multibyte split does not
    corrupt the tail. The marker matches the streaming surface so two
    truncation surfaces share vocabulary.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    elided = len(encoded) - max_bytes
    head = encoded[:max_bytes].decode("utf-8", errors="replace")
    return head + STREAM_TRUNCATION_MARKER_TEMPLATE.format(n=elided)


def run_argv(
    argv: list[str],
    *,
    allowed: Iterable[str],
    timeout_s: float,
    output_max_bytes: int,
) -> ShellResult:
    """Validate + spawn ``argv``; return a :class:`ShellResult`.

    The validator runs first; a :class:`ShellValidationError` is
    raised for the route layer to map (the body is therefore
    synchronous from the caller's perspective — no shell launches
    on a malformed argv).

    Timeouts kill the child and return :data:`ShellExitReason.TIMEOUT`
    with ``exit_code=-1``. Spawn errors (e.g. the binary missing on
    PATH) return :data:`ShellExitReason.SPAWN_ERROR` with
    ``exit_code=-1``.
    """
    cleaned = validate_argv(argv, allowed)
    import time

    start = time.monotonic()
    try:
        # ``shell=False`` always. ``capture_output=True`` so we can
        # truncate at a known byte budget rather than streaming.
        completed = subprocess.run(
            cleaned,
            shell=False,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # The child has been killed by ``run`` already; surface the
        # partial output if the kernel buffered any of it before
        # SIGKILL.
        elapsed = time.monotonic() - start
        stdout = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        return ShellResult(
            exit_code=-1,
            reason=ShellExitReason.TIMEOUT,
            stdout=_truncate(stdout, output_max_bytes),
            stderr=_truncate(stderr, output_max_bytes),
            duration_s=elapsed,
        )
    except (FileNotFoundError, PermissionError) as exc:
        elapsed = time.monotonic() - start
        return ShellResult(
            exit_code=-1,
            reason=ShellExitReason.SPAWN_ERROR,
            stdout="",
            stderr=str(exc),
            duration_s=elapsed,
        )
    elapsed = time.monotonic() - start
    return ShellResult(
        exit_code=completed.returncode,
        reason=ShellExitReason.EXITED,
        stdout=_truncate(
            completed.stdout.decode("utf-8", errors="replace"),
            output_max_bytes,
        ),
        stderr=_truncate(
            completed.stderr.decode("utf-8", errors="replace"),
            output_max_bytes,
        ),
        duration_s=elapsed,
    )


__all__ = [
    "ShellExitReason",
    "ShellResult",
    "ShellValidationError",
    "run_argv",
    "validate_argv",
]
