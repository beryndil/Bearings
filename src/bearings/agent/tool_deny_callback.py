"""Tool-deny BLOCKED-callback synthesis for orchestrator-driven executors.

Why this module exists. An autonomous Bearings executor running under
an orchestrator (`~/.claude/rules/executor-handoff-on-pressure.md`)
can have a tool call denied for several reasons:

1. The global `~/.claude/hooks/lockout.py` PreToolUse hook denies a
   `Write/Edit/MultiEdit/NotebookEdit` because the session is a reader
   on a project held by another writer. Deny text is prefixed with
   ``[lockout] `` (see `LOCKOUT_PREFIX`).
2. Anthropic's SDK / Claude Code permission gate denies a tool call
   for any other reason — settings-merge producing an effective `ask`
   default for tools not in the project's `permissions.allow`,
   future hook deny paths that don't use the lockout prefix, or any
   path that bypasses our own `ApprovalBroker`. Deny text is the
   SDK's canonical rejection message containing
   ``"The user doesn't want to proceed with this tool use"`` (see
   `SDK_REJECTION_SIGNATURE`).

In both cases the tool result text ends with the SDK's standard tail
"STOP what you are doing and wait for the user to tell you how to
proceed." For an interactive session that's fine — Dave types the
next instruction. For an autonomous executor it's a silent halt: the
executor stops, no `BLOCKED` callback gets POSTed to the
orchestrator's prompt endpoint, the orchestrator never wakes, the
audit stalls until a human notices.

The fix surface is here, inside the runner's post-tool-use event
handling. We watch every `ToolCallEnd`; when we see a deny that
matches either signature on ANY tool, we resolve the orchestrator id
from the executor's own `session_instructions` (set by the wiring
rule), synthesize a `BLOCKED — tool deny on <tool>: <reason>` line,
and dispatch it back into the orchestrator's prompt queue via the
runner's `_prompt_dispatch` closure (the same in-process path
`POST /api/sessions/{id}/prompt` takes — see
`bearings.api.ws_agent.build_runner` for the closure construction).

History:

- Audit item #519 introduced this module as `lockout_callback.py` with
  a narrow filter: only `Write/Edit/MultiEdit/NotebookEdit` and only
  ``[lockout] `` prefix. That covered the lockout-hook deny path but
  not the broader SDK-rejection path.
- Audit item #520 (this revision) renamed to `tool_deny_callback.py`,
  dropped the per-tool filter, and added the SDK-canonical signature.
  Driven by 2026-04-27 audit-#396 (item #520 plug): an executor under
  `bypassPermissions` had `mcp__bearings__bash` denied with the SDK
  rejection text, didn't match `[lockout]`, didn't match
  `LOCKED_TOOLS`, and silently halted for 12+ hours.

Failure modes (unchanged from #519):

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

The deny detection is conservative: only fires on the two known
signatures. Generic `is_error=True` tool results (e.g. an `Edit` with
a mismatched `old_string`, a `Bash` exit non-zero, a `curl` 404) are
left alone — they're tool-level failures that the agent is expected
to react to in-loop, not silent halts. A future deny path that uses
neither signature will silently disable this callback, which is the
right failure mode — better to miss a callback than to spam the
orchestrator with non-deny errors.
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

# Substring of the SDK's canonical "tool was denied" message. The full
# text is:
#   "The user doesn't want to proceed with this tool use. The tool use
#    was rejected (eg. if it was a file edit, the new_string was NOT
#    written to the file). STOP what you are doing and wait for the
#    user to tell you how to proceed."
# This shows up on EVERY denial that doesn't go through our lockout
# hook — settings-merge denies, future hook denies, anything routed
# through Anthropic's permission machinery rather than our broker.
# Substring match (not startswith) so the SDK is free to add a prefix
# without breaking us.
SDK_REJECTION_SIGNATURE = "The user doesn't want to proceed with this tool use"

# Cap on the deny-reason text included in the callback. Long messages
# bloat the orchestrator's prompt queue and clutter the stream view.
# 200 chars fits the lockout one-liner with room and truncates the
# verbose SDK rejection cleanly. Truncation marker is the standard
# Unicode ellipsis.
_MAX_REASON_CHARS = 200

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


def _is_deny_signature(error: str) -> bool:
    """True when `error` matches one of the known deny signatures.

    Conservative on purpose: a generic `is_error=True` tool result
    (Edit with mismatched old_string, Bash non-zero exit, curl 404)
    is NOT a deny — the agent reacts to it in-loop. Only signatures
    that produce a SILENT HALT need the callback synthesized."""
    if error.startswith(LOCKOUT_PREFIX):
        return True
    if SDK_REJECTION_SIGNATURE in error:
        return True
    return False


def _summarize_deny(error: str) -> str:
    """Compress a deny message down to a short, single-line summary
    so the BLOCKED callback stays readable in the orchestrator's
    stream view. The full message is still in the executor's tool-call
    history if Dave wants the verbose version.

    Rules:
    - Lockout deny: strip the `[lockout] ` prefix (the BLOCKED message
      already says "deny on <tool>"; restating "lockout" inflates noise
      without adding info — the original prefix is in the tool history).
    - SDK canonical rejection: rewrite to a short stable phrase. The
      SDK's stock text is long, identical on every deny, and uniquely
      uninformative ("the user doesn't want to..." when the user did
      not in fact decline anything — see audit #520 plug). The
      rewritten phrase points at the audit so a human reading the
      callback knows where the diagnosis lives.
    - Any other matched signature: take the first line, cap length.
    """
    if not error:
        return ""
    if SDK_REJECTION_SIGNATURE in error:
        return (
            "SDK rejected tool use (no [lockout] prefix; root cause may be "
            "settings-merge — see audit #520)"
        )
    first = error.splitlines()[0]
    if first.startswith(LOCKOUT_PREFIX):
        first = first[len(LOCKOUT_PREFIX) :]
    first = first.strip()
    if len(first) > _MAX_REASON_CHARS:
        first = first[: _MAX_REASON_CHARS - 1] + "…"
    return first


async def maybe_post_tool_deny_callback(
    runner: SessionRunner,
    *,
    tool_name: str,
    ok: bool,
    error: str | None,
) -> None:
    """If `event` represents a tool-deny on ANY tool (lockout-prefixed
    or SDK-canonical rejection), post a `BLOCKED — tool deny on
    <tool>: <reason>` callback to the executor's orchestrator.
    Otherwise no-op.

    Idempotent in spirit: every deny on every turn fires this; the
    orchestrator's prompt queue is already serial, and a pile-up of
    BLOCKED messages on a misbehaving executor is fine — Dave can read
    them. The path is short-circuited as cheaply as possible on the
    common (no-deny) case so the cost on a normal turn is one
    truthiness check + two substring checks."""
    if ok or not error:
        return
    if not _is_deny_signature(error):
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
            "tool_deny_callback: get_session failed for executor %s",
            runner.session_id,
        )
        return
    if row is None:
        return
    orch_id = _extract_orchestrator_id(row.get("session_instructions"))
    if orch_id is None:
        log.info(
            "tool_deny_callback: executor %s has no orchestrator in instructions; "
            "skipping callback (executor will halt as today)",
            runner.session_id,
        )
        return
    if orch_id == runner.session_id:
        # Defensive: a malformed instructions block that points at the
        # executor itself would re-enqueue our own runner forever.
        log.warning(
            "tool_deny_callback: executor %s lists itself as orchestrator; refusing self-dispatch",
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
            "tool_deny_callback: get_session failed for orchestrator %s",
            orch_id,
        )
        return
    if orch_row is None:
        log.warning(
            "tool_deny_callback: executor %s points at missing orchestrator %s",
            runner.session_id,
            orch_id,
        )
        return
    if orch_row.get("kind", "chat") not in _RUNNABLE_KINDS:
        log.warning(
            "tool_deny_callback: orchestrator %s has non-runnable kind %r; skipping",
            orch_id,
            orch_row.get("kind"),
        )
        return
    if orch_row.get("closed_at") is not None:
        log.warning(
            "tool_deny_callback: orchestrator %s is closed; skipping callback",
            orch_id,
        )
        return

    reason = _summarize_deny(error)
    content = f"BLOCKED — tool deny on {tool_name}: {reason}"
    try:
        await dispatch(orch_id, content)
    except Exception:  # noqa: BLE001 — never let callback failure crash a turn
        log.exception(
            "tool_deny_callback: dispatch to orchestrator %s failed; "
            "executor %s will halt without callback",
            orch_id,
            runner.session_id,
        )
        return
    log.info(
        "tool_deny_callback: posted BLOCKED to orchestrator %s for executor %s (tool=%s)",
        orch_id,
        runner.session_id,
        tool_name,
    )
