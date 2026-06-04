"""Backward-compat re-export shim for ``bearings.agent.sdk_loop``.

The SDK loop implementation has been split across:

* ``sdk_loop_core``   — main loop, turn execution, event dispatch
* ``sdk_loop_errors`` — error state, SDK option builders, _make_todo_update

This shim preserves ``from bearings.agent.sdk_loop import run_session_loop``
and ``from bearings.agent.sdk_loop import _do_run_one_turn`` (the latter is
used by ``tests/test_stop_event.py``).
"""

from __future__ import annotations

from bearings.agent.sdk_loop_core import (
    _do_run_one_turn,
    run_session_loop,
)

__all__ = [
    "_do_run_one_turn",
    "run_session_loop",
]
