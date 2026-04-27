"""Lockout-deny BLOCKED-callback synthesis for orchestrator-driven executors.

Why this module exists. The global `~/.claude/hooks/lockout.py`
PreToolUse hook denies `Write/Edit/MultiEdit/NotebookEdit` when the
session is a reader on a project held by another writer (or is
otherwise out-of-bounds). The Claude Agent SDK formats the rejection
text with the standard tail "STOP what you are doing and wait for the
user to tell you how to proceed." For an interactive session that's
fine — Dave types the next instruction. For an autonomous Bearings
executor running under an orchestrator
(`~/.claude/rules/executor-handoff-on-pressure.md`), it's a silent
halt: the executor stops, no `BLOCKED` callback gets POSTed to the
orchestrator's prompt endpoint, the orchestrator never wakes, the
audit stalls until a human notices.

The fix surface is here, inside the runner's post-tool-use event
handling. We watch every `ToolCallEnd`; when we see a deny that
matches the lockout signature (`tool_name in LOCKED_TOOLS` AND
`error.startswith("[lockout] ")`), we resolve the orchestrator id from
the executor's own `session_instructions` (set by the wiring rule),
synthesize a `BLOCKED — <reason>` line, and dispatch it back into the
orchestrator's prompt queue via the runner's `_prompt_dispatch`
closure (the same in-process path `POST /api/sessions/{id}/prompt`
takes — see `bearings.api.ws_agent.build_runner` for the closure
construction).

Failure modes:
- Executor has no `session_instructions` or no `Orchestrator: <id>`
  line → no callback (executor halts as today, behavior preserved
  for stand-alone bug sessions). Logged at INFO so it shows up in
  diagnostics without spamming WARN.
- Orchestrator session row missing / closed / non-runnable → no
  callback, logged at WARNING. (Different from "no orchestrator
  resolved" — this is "we have a target but it's broken.")
- `prompt_dispatch` is None (happens in unit tests that don't wire
  the full app) → no callback, no log spam.
- Dispatch raises → logged at WARNING and swallowed. The executor
  was about to halt anyway; a callback failure must not turn that
  into an unhandled-exception turn crash.

The deny detection itself is conservative: we only fire on the exact
prefix the hook produces. A future hook that rewrites the prefix will
silently disable this path, which is the right failure mode — better
to miss a callback than to spam the orchestrator with non-lockout
denies.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import aiosqlite

from bearings.db import store

if TYPE_CHECKING:
    from bearings.agent.runner import SessionRunner

log = logging.getLogger(__name__)

# Exact prefix emitted by `_deny()` in `~/.claude/hooks/lockout.py`.
# All deny paths in the hook construct messages that start with this
# literal. Matched against `ToolCallEnd.error` after `ok=False`.
LOCKOUT_PREFIX = "[lockout] "

# Tools the lockout hook is wired to deny. Any future expansion of the
# hook's matcher list MUST be reflected here, or the callback path
# silently stops firing for the new tool. (Sibling lockout-overdeny
# bug is tracked separately; both surfaces need to agree on this set.)
LOCKED_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})

# Matches the `Orchestrator: <id>` line in an executor's
# `session_instructions`, per the wiring shape in
# `~/.claude/rules/executor-handoff-on-pressure.md` §"Wiring a new
# master + executor set". Liberal id alphabet (hex + dashes) so a
# future shift to UUIDs-with-dashes doesn't break the parser.
_ORCH_LINE_RE = re.compile(
    r"^\s*Orchestrator:\s*([A-Za-z0-9-]{8,64})\s*$",
    re.MULTILINE,
)

# Runnable session kinds — mirrors `bearings.api.ws_agent.RUNNABLE_KINDS`.
# Imported lazily to avoid the agent → api circular at module load.
_RUNNABLE_KINDS = frozenset({"chat", "checklist"})


def _extract_orchestrator_id(session_instructions: str | None) -> str | None:
    """Pull the orchestrator session id from an executor's
    `session_instructions`. Returns None if the field is empty or no
    `Orchestrator: <id>` line is present."""
    if not session_instructions:
        return None
    match = _ORCH_LINE_RE.search(session_instructions)
    if match is None:
        return None
    return match.group(1)


def _summarize_deny(error: str) -> str:
    """Compress a multi-line lockout deny down to the first line so the
    BLOCKED callback stays readable in the orchestrator's stream view.
    The full message is still in the executor's tool-call history if
    Dave wants the verbose version."""
    first = error.splitlines()[0] if error else error
    # Strip the `[lockout] ` prefix from the summary — the BLOCKED
    # message says "lockout deny" already, so re-stating the prefix
    # doubles the visual noise.
    if first.startswith(LOCKOUT_PREFIX):
        first = first[len(LOCKOUT_PREFIX) :]
    return first.strip()


async def maybe_post_lockout_callback(
    runner: SessionRunner,
    *,
    tool_name: str,
    ok: bool,
    error: str | None,
) -> None:
    """If `event` represents a lockout-hook deny on a write-class tool,
    post a `BLOCKED — <reason>` callback to the executor's orchestrator.
    Otherwise no-op.

    Idempotent in spirit: every deny on every turn fires this; the
    orchestrator's prompt queue is already serial, and a pile-up of
    BLOCKED messages on a misbehaving executor is fine — Dave can read
    them. The path is short-circuited as cheaply as possible on the
    common (no-deny) case so the cost on a normal turn is one set
    membership check + one `startswith`."""
    if ok or not error:
        return
    if tool_name not in LOCKED_TOOLS:
        return
    if not error.startswith(LOCKOUT_PREFIX):
        return
    dispatch = getattr(runner, "_prompt_dispatch", None)
    if dispatch is None:
        # Unit-test path or a runner constructed outside `build_runner`.
        # Don't log here — silent skip keeps tests quiet and the production
        # `build_runner` always wires a real dispatcher anyway.
        return

    # Resolve orchestrator id from the executor's own session_instructions.
    try:
        row = await store.get_session(runner.db, runner.session_id)
    except aiosqlite.Error:
        log.exception(
            "lockout_callback: get_session failed for executor %s",
            runner.session_id,
        )
        return
    if row is None:
        return
    orch_id = _extract_orchestrator_id(row.get("session_instructions"))
    if orch_id is None:
        log.info(
            "lockout_callback: executor %s has no orchestrator in instructions; "
            "skipping callback (executor will halt as today)",
            runner.session_id,
        )
        return
    if orch_id == runner.session_id:
        # Defensive: a malformed instructions block that points at the
        # executor itself would re-enqueue our own runner forever.
        log.warning(
            "lockout_callback: executor %s lists itself as orchestrator; refusing self-dispatch",
            runner.session_id,
        )
        return

    # Verify the orchestrator session is reachable + runnable. Mirrors
    # the gates `inject_prompt` enforces at the HTTP boundary so the
    # callback path doesn't get "smarter" than the public contract.
    try:
        orch_row = await store.get_session(runner.db, orch_id)
    except aiosqlite.Error:
        log.exception(
            "lockout_callback: get_session failed for orchestrator %s",
            orch_id,
        )
        return
    if orch_row is None:
        log.warning(
            "lockout_callback: executor %s points at missing orchestrator %s",
            runner.session_id,
            orch_id,
        )
        return
    if orch_row.get("kind", "chat") not in _RUNNABLE_KINDS:
        log.warning(
            "lockout_callback: orchestrator %s has non-runnable kind %r; skipping",
            orch_id,
            orch_row.get("kind"),
        )
        return
    if orch_row.get("closed_at") is not None:
        log.warning(
            "lockout_callback: orchestrator %s is closed; skipping callback",
            orch_id,
        )
        return

    reason = _summarize_deny(error)
    content = f"BLOCKED — lockout deny on {tool_name}: {reason}"
    try:
        await dispatch(orch_id, content)
    except Exception:  # noqa: BLE001 — never let callback failure crash a turn
        log.exception(
            "lockout_callback: dispatch to orchestrator %s failed; "
            "executor %s will halt without callback",
            orch_id,
            runner.session_id,
        )
        return
    log.info(
        "lockout_callback: posted BLOCKED to orchestrator %s for executor %s (tool=%s)",
        orch_id,
        runner.session_id,
        tool_name,
    )
