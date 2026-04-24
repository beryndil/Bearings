"""Temporary diagnostic probe for the intermittent
'Claude interrupted on session switch' bug (2026-04-23).

Writes one line per interrupt-triggering event to
``$XDG_DATA_HOME/bearings/interrupt-probe.log``
(default ``~/.local/share/bearings/interrupt-probe.log``).

Instrumented sites:

- ``agent/session.py:AgentSession.interrupt`` — the actual SDK
  ``client.interrupt()`` call. Fires for every real interrupt no matter
  which upstream caller triggered it.
- ``agent/runner.py:SessionRunner.shutdown`` — right after
  ``_stop_requested = True`` is set. Identifies the external caller
  (delete-session, reorg, app shutdown) via the captured stack chain.
- ``agent/runner.py:SessionRunner.request_stop`` — same, for the
  user-initiated Stop path (UI Stop button or reorg `request_stop`).
- ``api/ws_agent.py`` finally block — records every WebSocket
  disconnect with the runner's ``is_running`` state at the moment,
  so timing can be correlated with any interrupt that fires around it.

Each log line carries ``site=``, ``session=``, a ``chain=`` of the
calling frames, and site-specific ``key=value`` extras. Remove this
file and its four call sites once the session-switch interrupt is
pinned down — see TODO.md (2026-04-23 entry)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_LOGGER_NAME = "bearings.interrupt_probe"


def _log_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "bearings" / "interrupt-probe.log"


_configured = False


def _ensure_logger() -> logging.Logger:
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return logger
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s.%(msecs)03d %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        # Don't leak probe lines into the main bearings log — they're
        # noise outside this diagnostic.
        logger.propagate = False
    except Exception:
        # The probe is a diagnostic, never fatal. If we can't write the
        # log file, skip silently — the main app must keep running.
        pass
    _configured = True
    return logger


def _caller_chain(max_depth: int = 6) -> str:
    """Best-effort call-site chain for this probe invocation.

    Skips the probe module's own frames so the chain starts at the
    instrumented call site itself."""
    parts: list[str] = []
    depth = 1
    while depth < max_depth + 4:
        try:
            frame = sys._getframe(depth)
        except ValueError:
            break
        filename = Path(frame.f_code.co_filename).name
        if filename != "_interrupt_probe.py":
            parts.append(f"{filename}:{frame.f_lineno}({frame.f_code.co_name})")
            if len(parts) >= max_depth:
                break
        depth += 1
    return " <- ".join(parts)


def probe(site: str, session_id: str, **extra: object) -> None:
    """Record that an interrupt-triggering site fired.

    Call this as the first statement inside the code path you want to
    capture. Never raises — a probe that crashes the app would be worse
    than no probe."""
    try:
        logger = _ensure_logger()
        parts = [
            f"site={site}",
            f"session={session_id}",
            f"chain=[{_caller_chain()}]",
        ]
        for key, value in extra.items():
            parts.append(f"{key}={value}")
        logger.info(" ".join(parts))
    except Exception:
        pass
