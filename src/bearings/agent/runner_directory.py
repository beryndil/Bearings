"""Per-runner Directory Context System lifecycle.

Owns the start/end markers a runner appends to
`<working_dir>/.bearings/history.jsonl`, plus the fire-and-forget
revalidation and `on_open.sh` kickoffs that piggyback on the first
WS attach.

Why split out: the runner outlives WS reconnects, but the start
marker should land exactly once per runner-lifetime. Keeping the
idempotency guard, the lifecycle handle, and the end-marker write
in one place makes the contract obvious — and lets `runner.py` stay
under the project's 400-line cap.

Extracted from `runner.py` 2026-04-30.
"""

from __future__ import annotations

import asyncio

from bearings.agent.session import AgentSession
from bearings.bearings_dir import lifecycle as dir_lifecycle


class DirectoryLifecycle:
    """One-shot start + matched end markers for a runner. Construct
    per-runner; call `note_start()` on every WS attach (idempotent)
    and `note_end()` once during shutdown."""

    def __init__(self, session_id: str, agent: AgentSession) -> None:
        self._session_id = session_id
        self._agent = agent
        # Captured by `note_start` on the first WS connection and
        # consumed by `note_end` to append the matching end-marker.
        # Stays `None` for directories that haven't been onboarded
        # yet — the start hook no-ops there and the end hook checks
        # for `None`.
        self._handle: dir_lifecycle.SessionLifecycleHandle | None = None
        # Idempotency guard: `note_start` is called on every WS
        # connection (the runner outlives reconnects), but the
        # history-jsonl start marker should land exactly once per
        # runner lifetime. True after the first call regardless of
        # whether the directory was onboarded — re-calling on a
        # non-onboarded directory shouldn't pay the FS-stat tax on
        # every reconnect.
        self._start_attempted: bool = False

    async def note_start(self) -> None:
        """Idempotent one-shot. Stamps the `history.jsonl` start
        marker and kicks off stale-state revalidation in the
        background. Safe to call on every WS attach — the worst case
        is a single FS-stat for a non-onboarded directory.

        Async-safe: both the start-marker write and the revalidation
        pass through `asyncio.to_thread` so the event loop never
        blocks on git or `uv sync`."""
        if self._start_attempted:
            return
        self._start_attempted = True
        working_dir = self._agent.working_dir
        if not working_dir:
            return
        # History start marker: cheap, but still synchronous I/O —
        # offload so a slow disk doesn't stall the WS handler.
        self._handle = await asyncio.to_thread(
            dir_lifecycle.record_session_start, working_dir, self._session_id
        )
        # Stale-state revalidation: fire-and-forget. Wraps the
        # subprocess-heavy `run_check` in a task so the user starts
        # typing immediately. The brief renders from whatever's on
        # disk; the revalidation result lands on the *next* turn.
        asyncio.create_task(
            asyncio.to_thread(dir_lifecycle.maybe_revalidate, working_dir),
            name=f"dir-revalidate:{self._session_id}",
        )
        # User-defined `.bearings/checks/on_open.sh` (v0.6.3 polish):
        # fire-and-forget too. The 10s subprocess budget runs in a
        # worker thread so a slow check doesn't hold the WS attach.
        # Result is persisted to `.bearings/last_on_open.json`; the
        # brief reads it on the next turn.
        asyncio.create_task(
            asyncio.to_thread(dir_lifecycle.maybe_run_on_open, working_dir),
            name=f"dir-on-open:{self._session_id}",
        )

    async def note_end(self) -> None:
        """Append the matching end-marker to `history.jsonl`.
        Synchronous git lookups + JSONL append, so we offload to a
        thread to keep the event loop honest. No-op when start was
        never recorded (non-onboarded directory)."""
        handle = self._handle
        self._handle = None
        if handle is not None:
            await asyncio.to_thread(dir_lifecycle.record_session_end, handle)
