"""Background workflow file watcher — surfaces harness workflow progress to the UI.

The Claude Code harness writes workflow progress journals to disk at:

    ``~/.claude/projects/<cwd-slug>/<sdk-uuid>/workflows/wf_<id>.json``

Bearings can derive the project slug and SDK UUID from a session's
``working_dir`` and ``session_id`` (via :func:`bearings_to_sdk_uuid`),
but the watcher uses a broader strategy: it scans all paths matching
``~/.claude/projects/*/*/workflows/wf_*.json`` every
:data:`bearings.config.constants.WORKFLOW_POLL_INTERVAL_S` seconds,
extracts the SDK UUID from the path, converts to a Bearings session ID,
and fans workflow progress events to the
:class:`bearings.web.routes.ws_sessions.SessionsBroadcaster`.

This gives complete coverage of all sessions' workflows without
pre-registration: even idle/reaped sessions whose workflows are still
running get their progress surfaced.

**Kill detection**: the watcher detects terminal states
(``"completed"``, ``"killed"``, ``"error"``) by reading the journal's
``status`` field on every poll. Terminal events are emitted once, then
the run is moved to the ``_done`` set so subsequent polls skip it.

**State tracking**: ``_seen`` maps ``run_id`` → last modification time
so we only re-read files that actually changed. ``_done`` is the set of
run IDs whose terminal event has been emitted; they are never read again.

**Path → session_id mapping**:

    ``~/.claude/projects/<slug>/<sdk-uuid>/workflows/wf_xxx.json``
    → ``sdk_uuid_to_bearings("<sdk-uuid>")``

This is a pure function with no DB access; the watcher does not need a
DB connection.

**Layer**: ``agent/`` (no FastAPI imports). The broadcaster is injected
at construction to keep the layer boundary clean.

References:

* ``docs/architecture-v1.md`` §3.1 — agent layer must not import web.
* ``bearings.config.constants.WORKFLOW_POLL_INTERVAL_S`` — cadence.
* ``bearings.agent.sdk_session_id.sdk_uuid_to_bearings`` — path mapping.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from bearings.agent.sdk_session_id import sdk_uuid_to_bearings
from bearings.config.constants import WORKFLOW_POLL_INTERVAL_S

_log = logging.getLogger(__name__)


@runtime_checkable
class WorkflowProgressPublisher(Protocol):
    """Structural interface satisfied by :class:`SessionsBroadcaster`.

    Defined in the ``agent`` layer so :class:`WorkflowWatcher` does not
    import from ``bearings.web`` (arch §3.1 rule #4 — no agent → web
    imports). The concrete ``SessionsBroadcaster`` satisfies this Protocol
    structurally; ``isinstance`` checks work because ``@runtime_checkable``
    is set (useful in tests that pass a mock broadcaster).
    """

    def publish_workflow_progress(self, state: WorkflowState) -> None:
        """Fan out a ``workflow_progress`` frame for ``state``."""
        ...


# Glob pattern relative to ``~/.claude/projects/`` that finds all
# workflow journals across all projects and sessions.
_WORKFLOW_GLOB: Final[str] = "*/*/workflows/wf_*.json"

# ``status`` values the harness writes when a workflow run is terminal.
# Any run whose ``status`` field matches one of these values will have
# its final event emitted exactly once, then be moved to ``_done``.
_TERMINAL_STATUSES: Final[frozenset[str]] = frozenset({"completed", "killed", "error"})

# Depth from ``~/.claude/projects/`` at which the SDK UUID directory
# lives: ``<slug>/<uuid>/workflows/wf_*.json``.
# Path component indices (from root):
#   …/projects/<slug>/<uuid>/workflows/wf_*.json
# Counting from the left of ``parts``: the UUID is at -3 relative to
# the file, or equivalently at index 2 from ``projects/``.
_SDK_UUID_INDEX_FROM_FILE: Final[int] = 3


@dataclass(frozen=True)
class WorkflowState:
    """Live snapshot of one workflow run used for fan-out.

    All counts are non-negative integers. ``current_phase`` is ``None``
    before the first phase marker appears in the journal.
    """

    session_id: str
    run_id: str
    workflow_name: str
    status: str  # "running" | "completed" | "killed" | "error"
    current_phase: str | None
    agents_running: int
    agents_done: int
    agents_queued: int
    started_at: int  # Unix timestamp in milliseconds


def _parse_journal(path: Path, session_id: str) -> WorkflowState | None:
    """Read a workflow journal file and return a :class:`WorkflowState`.

    Returns ``None`` when the file cannot be parsed or is missing the
    mandatory ``runId`` field. Errors are logged at WARNING level so
    one bad journal does not break the watcher loop.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        _log.warning("workflow_watcher: cannot read %s: %s", path, exc)
        return None

    try:
        data: dict[str, object] = json.loads(raw)
    except json.JSONDecodeError as exc:
        _log.warning("workflow_watcher: JSON parse error in %s: %s", path, exc)
        return None

    run_id = data.get("runId")
    if not isinstance(run_id, str) or not run_id:
        _log.warning("workflow_watcher: missing runId in %s", path)
        return None

    status = data.get("status")
    if not isinstance(status, str):
        status = "running"

    workflow_name = data.get("workflowName") or data.get("name") or run_id
    if not isinstance(workflow_name, str):
        workflow_name = run_id

    # Extract current phase and agent counts from ``workflowProgress``.
    current_phase: str | None = None
    agents_running = 0
    agents_done = 0
    agents_queued = 0

    progress = data.get("workflowProgress")
    if isinstance(progress, list):
        # Reverse scan so we find the most recent phase header first.
        for entry in reversed(progress):
            if not isinstance(entry, dict):
                continue
            if entry.get("type") == "workflow_phase" and current_phase is None:
                title = entry.get("title")
                if isinstance(title, str):
                    current_phase = title

        # Forward pass for agent counts.
        for entry in progress:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") != "workflow_agent":
                continue
            state = entry.get("state")
            if state == "done":
                agents_done += 1
            elif state == "running":
                agents_running += 1
            else:
                # "queued" or unknown — treat as queued.
                agents_queued += 1

    start_time = data.get("startTime")
    if not isinstance(start_time, int):
        start_time = 0

    return WorkflowState(
        session_id=session_id,
        run_id=run_id,
        workflow_name=workflow_name,
        status=status,
        current_phase=current_phase,
        agents_running=agents_running,
        agents_done=agents_done,
        agents_queued=agents_queued,
        started_at=start_time,
    )


def _extract_session_id_from_path(path: Path) -> str | None:
    """Derive a Bearings session id from a workflow journal path.

    Expected structure (counting from the journal file):
    ``…/projects/<slug>/<sdk-uuid>/workflows/wf_xxx.json``

    Returns ``None`` when the path does not have enough components or
    the UUID conversion fails (silently — bad path is not an error
    from the watcher's perspective).
    """
    parts = path.parts
    # Need at least: projects / <slug> / <sdk-uuid> / workflows / wf_xxx.json
    if len(parts) < _SDK_UUID_INDEX_FROM_FILE + 1:
        return None
    sdk_uuid = parts[-_SDK_UUID_INDEX_FROM_FILE]
    try:
        return sdk_uuid_to_bearings(sdk_uuid)
    except ValueError:
        # The directory name isn't a valid SDK UUID — not a workflow path
        # we own (e.g. a nested project or a different harness layout).
        return None


class WorkflowWatcher:
    """Async polling watcher for Claude Code workflow journals.

    Lifecycle: construct with a :class:`SessionsBroadcaster`, then call
    :meth:`run` as an asyncio task.  :meth:`run` loops forever until
    cancelled; the caller (``web/app.py`` lifespan) cancels on shutdown.

    The ``projects_root`` constructor argument defaults to
    ``~/.claude/projects`` and is overridable in tests so the watcher
    can scan a ``tmp_path`` directory without touching the real
    harness data.

    State is isolated to each :class:`WorkflowWatcher` instance — safe
    to construct per-test without shared-state crosstalk.
    """

    def __init__(
        self,
        broadcaster: WorkflowProgressPublisher,
        *,
        projects_root: Path | None = None,
        poll_interval_s: float = WORKFLOW_POLL_INTERVAL_S,
    ) -> None:
        if poll_interval_s <= 0:
            raise ValueError(f"poll_interval_s must be > 0 (got {poll_interval_s})")
        self._broadcaster = broadcaster
        self._projects_root: Path = (
            projects_root if projects_root is not None else Path.home() / ".claude" / "projects"
        )
        self._poll_interval_s = poll_interval_s
        # run_id → last known mtime (float, st_mtime). Re-read only when mtime changes.
        self._seen: dict[str, float] = {}
        # run IDs whose terminal event has been emitted; skip on next polls.
        self._done: set[str] = set()

    async def run(self) -> None:
        """Poll loop — runs until cancelled.

        ``asyncio.CancelledError`` is NOT caught so the task exits
        cleanly on shutdown (the caller's ``await task`` propagates it).
        """
        while True:
            await asyncio.sleep(self._poll_interval_s)
            try:
                self._poll_once()
            except Exception:
                # Transient filesystem or other error — log and continue
                # so a single bad poll cycle doesn't kill the watcher.
                _log.exception("workflow_watcher: unexpected error during poll")

    def _poll_once(self) -> None:
        """Single poll: scan and fan out changed workflow journals."""
        if not self._projects_root.is_dir():
            return
        for path in self._projects_root.glob(_WORKFLOW_GLOB):
            self._process_file(path)

    def _process_file(self, path: Path) -> None:
        """Check ``path`` for changes and fan out an event if needed."""
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            return

        session_id = _extract_session_id_from_path(path)
        if session_id is None:
            return

        # Read the run_id from the file to use as key. We need the run_id
        # before we can check ``_done``; use the filename stem as a fast
        # proxy (``wf_<id>.json`` → ``wf_<id>``).
        run_key = path.stem  # e.g. "wf_99657639-dbc"

        if run_key in self._done:
            return  # terminal event already emitted; skip forever.

        last_mtime = self._seen.get(run_key)
        if last_mtime is not None and mtime <= last_mtime:
            return  # file unchanged since last poll.

        state = _parse_journal(path, session_id)
        if state is None:
            return

        # Update seen timestamp *before* fan-out so a slow broadcaster
        # doesn't cause duplicate events.
        self._seen[run_key] = mtime

        # Fan out via the sessions broadcaster. The broadcaster's
        # ``publish_workflow_progress`` method is synchronous (same
        # design contract as the other ``publish_*`` methods) — no await.
        self._broadcaster.publish_workflow_progress(state)

        if state.status in _TERMINAL_STATUSES:
            self._done.add(run_key)
            _log.info(
                "workflow_watcher: run %s in session %s reached terminal status %r",
                state.run_id,
                state.session_id,
                state.status,
            )


__all__ = [
    "WorkflowProgressPublisher",
    "WorkflowState",
    "WorkflowWatcher",
]
