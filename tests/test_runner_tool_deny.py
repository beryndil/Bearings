"""Tests for `bearings.agent.tool_deny_callback`.

Audit items #519 + #520. The runner watches every `ToolCallEnd` for
deny signatures that would silently halt an autonomous executor:

  1. ``[lockout] `` prefix (audit #519): the global
     `~/.claude/hooks/lockout.py` PreToolUse hook denying a write-class
     tool because the session is a reader on a project held by another
     writer.
  2. ``"The user doesn't want to proceed with this tool use"`` substring
     (audit #520): the SDK's canonical rejection text, fired by
     Anthropic's permission gate when settings-merge / future hook /
     other path denies a tool BEFORE our `ApprovalBroker` sees it.

Either signature on ANY tool produces a `BLOCKED — tool deny on
<tool>: <reason>` callback to the executor's orchestrator. Generic
`is_error=True` results (Edit with mismatched old_string, Bash exit
non-zero, curl 404) must NOT fire — those are tool-level failures the
agent reacts to in-loop.

These tests pin five contracts:

  1. Lockout deny on a write-class tool + executor with
     `Orchestrator: <id>` in `session_instructions` →
     `prompt_dispatch` is called once with
     `(orchestrator_id, "BLOCKED — tool deny on Write: ...")`.
     The happy path that the 2026-04-27 audit-#384 incident wanted.
  2. SDK-canonical deny on `mcp__bearings__bash` → callback fires.
     The 2026-04-27 audit-#396 incident — `bash` is not a write tool
     and the deny text doesn't carry the lockout prefix, so the #519
     filter missed it. #520 must catch it.
  3. SDK-canonical deny on assorted non-Write tools (`Read`, `Bash`,
     `Glob`) → callback fires. Defense-in-depth across tool surfaces.
  4. Lockout deny + executor with no orchestrator hint → no callback;
     executor halts as today. Stand-alone bug sessions must not
     regress.
  5. Generic non-deny tool failure → no callback. The sniffer is
     conservative; ordinary `is_error=True` results must NOT fire.

Fixtures mirror `tests/test_agent_artifacts.py`'s `ScriptedAgent` shape:
single turn per test, real sqlite DB, the runner driven through one
`submit_prompt` end-to-end.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiosqlite
import pytest

from bearings.agent.events import (
    AgentEvent,
    MessageComplete,
    MessageStart,
    ToolCallEnd,
    ToolCallStart,
)
from bearings.agent.runner import SessionRunner
from bearings.agent.session import AgentSession
from bearings.agent.tool_deny_callback import (
    LOCKOUT_PREFIX,
    SDK_REJECTION_SIGNATURE,
    _extract_orchestrator_id,
    _is_deny_signature,
    _summarize_deny,
)
from bearings.db import store
from bearings.db._common import init_db

# Full canonical SDK rejection text — the exact string Anthropic
# injects into a tool result when a permission gate denies the call
# (any path: settings-merge, hook, dismissed UI). Confirmed in
# `~/.claude/projects/.../abab3b15-77cc-42c6-babe-12db579a0eca.jsonl`
# line 78 (audit #520 reference incident).
SDK_REJECTION_FULL = (
    "The user doesn't want to proceed with this tool use. The tool use was "
    "rejected (eg. if it was a file edit, the new_string was NOT written to "
    "the file). STOP what you are doing and wait for the user to tell you how "
    "to proceed."
)


class ScriptedAgent(AgentSession):
    """Minimal stub from `test_runner.py`: one event-list per turn."""

    def __init__(self, session_id: str, scripts: list[list[AgentEvent]]) -> None:
        super().__init__(session_id, working_dir="/tmp", model="m")
        self._scripts = scripts
        self.prompts: list[str] = []

    async def stream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        self.prompts.append(prompt)
        script = self._scripts.pop(0) if self._scripts else []
        for event in script:
            yield event


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    """Real sqlite + one executor session and one orchestrator session.
    Per-test DB so `prompt_dispatch` assertions don't bleed across
    cases."""
    conn = await init_db(tmp_path / "tool-deny.sqlite")
    # Orchestrator (created first so its id is stable for instructions).
    orch = await store.create_session(conn, working_dir="/tmp", model="m", title="orchestrator")
    # Executor — instructions wired per
    # `~/.claude/rules/executor-handoff-on-pressure.md` §"Wiring".
    exec_row = await store.create_session(conn, working_dir="/tmp", model="m", title="executor")
    await store.update_session(
        conn,
        exec_row["id"],
        fields={
            "session_instructions": (
                f"Master: master-id\nOrchestrator: {orch['id']}\nItem: #520\n"
            ),
        },
    )
    yield conn
    await conn.close()


async def _ids(conn: aiosqlite.Connection) -> tuple[str, str]:
    """Return (executor_id, orchestrator_id) — fixture inserts orch
    first, executor second."""
    rows = await store.list_sessions(conn)
    rows_sorted = sorted(rows, key=lambda r: r["created_at"])
    orch_id = rows_sorted[0]["id"]
    exec_id = rows_sorted[1]["id"]
    return exec_id, orch_id


def _deny_script(
    sid: str,
    *,
    tool_name: str,
    error: str,
) -> list[AgentEvent]:
    """4-event turn: MessageStart → ToolCallStart → failed ToolCallEnd
    → MessageComplete. Mirrors what the SDK emits when a deny path
    fires: a synthetic tool result with `is_error=True` and the deny
    `message` in the `error` field of the Bearings `ToolCallEnd`
    translation (per `_events_mixin._tool_call_end`)."""
    return [
        MessageStart(session_id=sid, message_id="msg-1"),
        ToolCallStart(
            session_id=sid,
            tool_call_id="tool-1",
            name=tool_name,
            input={"file_path": "/some/path"},
        ),
        ToolCallEnd(
            session_id=sid,
            tool_call_id="tool-1",
            ok=False,
            output=None,
            error=error,
        ),
        MessageComplete(session_id=sid, message_id="msg-1", cost_usd=None),
    ]


async def _drain_until_complete(queue: asyncio.Queue[Any], timeout: float = 2.0) -> None:
    """Pull envelopes off the subscriber queue until `message_complete`
    arrives. Used purely as a sync-point so the test asserts after the
    runner's worker has processed the ToolCallEnd arm in full."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise AssertionError("message_complete did not arrive within timeout")
        env = await asyncio.wait_for(queue.get(), timeout=remaining)
        if env.payload["type"] == "message_complete":
            return


async def _run_one_turn(runner: SessionRunner, prompt: str = "do it") -> None:
    queue, _ = await runner.subscribe(0)
    runner.start()
    try:
        await runner.submit_prompt(prompt)
        await _drain_until_complete(queue)
    finally:
        await runner.shutdown()


async def _run_deny_capturing_dispatch(
    db: aiosqlite.Connection,
    *,
    tool_name: str,
    error: str,
) -> tuple[list[tuple[str, str]], str]:
    """Helper: install a deny script for `tool_name` with `error`,
    drive the runner one turn, return the captured `(target, content)`
    dispatch calls plus the orchestrator id for assertion convenience.
    Used by the parametric SDK-rejection table-tests."""
    exec_id, orch_id = await _ids(db)
    calls: list[tuple[str, str]] = []

    async def fake_dispatch(target_id: str, content: str) -> None:
        calls.append((target_id, content))

    script = _deny_script(exec_id, tool_name=tool_name, error=error)
    runner = SessionRunner(
        exec_id,
        ScriptedAgent(exec_id, scripts=[script]),
        db,
        prompt_dispatch=fake_dispatch,
    )
    await _run_one_turn(runner)
    return calls, orch_id


# ---- pure-helper unit tests ----------------------------------------


def test_extract_orchestrator_id_happy() -> None:
    text = "Master: aaaa\nOrchestrator: 33befa3dd7c44c5da62554b01defaf96\nItem: #520\n"
    assert _extract_orchestrator_id(text) == "33befa3dd7c44c5da62554b01defaf96"


def test_extract_orchestrator_id_missing() -> None:
    assert _extract_orchestrator_id("Master: x\nItem: y\n") is None
    assert _extract_orchestrator_id("") is None
    assert _extract_orchestrator_id(None) is None


def test_summarize_deny_strips_lockout_prefix_and_keeps_first_line() -> None:
    msg = (
        "[lockout] You are a reader on /home/beryndil/Projects/Bearings.\n"
        "Run `/lockout claim-writer` to take over.\n"
    )
    assert _summarize_deny(msg) == "You are a reader on /home/beryndil/Projects/Bearings."


def test_summarize_deny_rewrites_sdk_rejection_to_short_phrase() -> None:
    """The SDK's canonical rejection text is long, identical on every
    deny, and uniquely uninformative. The summarizer rewrites it to a
    short stable phrase pointing at audit #520 so a human reading the
    BLOCKED callback knows where the diagnosis lives."""
    summary = _summarize_deny(SDK_REJECTION_FULL)
    assert "SDK rejected tool use" in summary
    assert "#520" in summary
    # Must NOT echo the wrong-attribution "user doesn't want" phrasing
    # that the SDK injected — the user did not in fact decline.
    assert "doesn't want" not in summary


def test_summarize_deny_caps_long_first_line() -> None:
    """Pathological lockout deny with a 500-char first line gets
    truncated cleanly so the orchestrator's prompt queue and stream
    view aren't bloated."""
    long_msg = "[lockout] " + ("x" * 500)
    summary = _summarize_deny(long_msg)
    assert summary.endswith("…")
    assert len(summary) <= 200


def test_is_deny_signature_matches_lockout_and_sdk() -> None:
    assert _is_deny_signature("[lockout] reader on /tmp.")
    assert _is_deny_signature(SDK_REJECTION_FULL)
    # SDK signature embedded inside a longer SDK-prefix-with-extra is
    # still a match (substring not startswith — defense against future
    # Anthropic decorators around the rejection text).
    assert _is_deny_signature("Some Anthropic prefix: " + SDK_REJECTION_FULL + " trailing")


def test_is_deny_signature_skips_generic_failures() -> None:
    """Ordinary tool errors must NOT match — those are agent-loop
    feedback, not silent halts."""
    assert not _is_deny_signature("String to replace not found in file.")
    assert not _is_deny_signature("Command failed with exit code 1")
    assert not _is_deny_signature("HTTP 404 Not Found")
    assert not _is_deny_signature("")


def test_constants_are_stable() -> None:
    """Tripwire on the two signatures the callback synthesizer keys on.
    A future change to either string in the SDK or our hook MUST be
    matched here, or the callback path silently stops firing."""
    assert LOCKOUT_PREFIX == "[lockout] "
    assert SDK_REJECTION_SIGNATURE == "The user doesn't want to proceed with this tool use"


# ---- end-to-end runner tests ---------------------------------------


@pytest.mark.asyncio
async def test_lockout_deny_posts_blocked_callback(
    db: aiosqlite.Connection,
) -> None:
    """Audit #519 happy path preserved: `Write` denied with a
    `[lockout] ...` message → `prompt_dispatch` is called exactly once
    with the orchestrator id and a BLOCKED-prefixed content line
    carrying the tool name and the deny reason."""
    deny_msg = (
        "[lockout] You are a reader on /home/beryndil/Projects/Bearings. "
        "Run `/lockout claim-writer`."
    )
    calls, orch_id = await _run_deny_capturing_dispatch(db, tool_name="Write", error=deny_msg)
    assert len(calls) == 1, f"expected one BLOCKED dispatch, got {calls!r}"
    target, content = calls[0]
    assert target == orch_id
    assert content.startswith("BLOCKED — tool deny on Write: ")
    assert "reader" in content


@pytest.mark.asyncio
async def test_sdk_rejection_on_mcp_bash_posts_blocked_callback(
    db: aiosqlite.Connection,
) -> None:
    """Audit #520 reference incident: `mcp__bearings__bash` denied
    with the SDK's canonical rejection text (no `[lockout]` prefix,
    not in #519's `LOCKED_TOOLS` set). The 2026-04-27 audit-#396
    executor stalled silently for 12+ hours on this exact shape;
    the broadened sniffer must now catch it and POST BLOCKED to the
    orchestrator."""
    calls, orch_id = await _run_deny_capturing_dispatch(
        db, tool_name="mcp__bearings__bash", error=SDK_REJECTION_FULL
    )
    assert len(calls) == 1, f"expected one BLOCKED dispatch, got {calls!r}"
    target, content = calls[0]
    assert target == orch_id
    assert content.startswith("BLOCKED — tool deny on mcp__bearings__bash: ")
    assert "SDK rejected" in content
    # The verbose, misleading "user doesn't want" phrasing must NOT
    # leak into the orchestrator stream — the rewrite covers it.
    assert "doesn't want" not in content


@pytest.mark.parametrize("tool_name", ["Read", "Bash", "Glob"])
@pytest.mark.asyncio
async def test_sdk_rejection_on_assorted_non_write_tools_posts_callback(
    db: aiosqlite.Connection,
    tool_name: str,
) -> None:
    """Defense-in-depth: SDK-canonical deny on tools that #519 would
    have skipped (Read, Bash, Glob — none in `LOCKED_TOOLS`) now fires
    the callback. Closes the broader silent-halt class beyond the
    specific `mcp__bearings__bash` instance documented in the plug."""
    calls, orch_id = await _run_deny_capturing_dispatch(
        db, tool_name=tool_name, error=SDK_REJECTION_FULL
    )
    assert len(calls) == 1, f"expected BLOCKED for {tool_name}, got {calls!r}"
    target, content = calls[0]
    assert target == orch_id
    assert content == (
        f"BLOCKED — tool deny on {tool_name}: SDK rejected tool use "
        "(no [lockout] prefix; root cause may be settings-merge — see audit #520)"
    )


@pytest.mark.asyncio
async def test_lockout_deny_on_non_write_tool_posts_callback(
    db: aiosqlite.Connection,
) -> None:
    """#520 widens the contract: a `[lockout] `-prefixed deny on ANY
    tool now fires the callback, not just write-class tools.

    This test inverts the #519 contract pinned by
    `test_lockout_deny_on_non_locked_tool_skips_callback` (now
    retired). Rationale: the original `LOCKED_TOOLS` filter was
    defensive against future hook expansion, but it created a silent
    failure class — any future hook deny on a non-write tool would be
    swallowed. Per #520, the deny signature alone (not the tool set)
    determines whether to synthesize a callback."""
    calls, orch_id = await _run_deny_capturing_dispatch(
        db,
        tool_name="Bash",
        error="[lockout] hypothetical future hook deny on Bash.",
    )
    assert len(calls) == 1, f"expected BLOCKED for Bash, got {calls!r}"
    target, content = calls[0]
    assert target == orch_id
    assert content.startswith("BLOCKED — tool deny on Bash: ")
    assert "hypothetical future hook" in content


@pytest.mark.parametrize(
    ("tool_name", "error"),
    [
        ("Edit", "[lockout] /tmp held by writer deadbeef."),
        ("mcp__bearings__bash", SDK_REJECTION_FULL),
    ],
    ids=["lockout-prefixed", "sdk-canonical"],
)
@pytest.mark.asyncio
async def test_deny_with_no_orchestrator_skips_callback(
    db: aiosqlite.Connection,
    tool_name: str,
    error: str,
) -> None:
    """Stand-alone executor (no `Orchestrator:` line in
    `session_instructions`) hits a deny → no callback, no crash. Pins
    the no-regression contract for one-off bug sessions that aren't
    part of an orchestrator/audit pattern. Parametrized over both
    signatures so the new SDK-canonical path inherits the same gate
    the lockout path already enforced under #519."""
    exec_id, _orch_id = await _ids(db)
    await store.update_session(
        db, exec_id, fields={"session_instructions": "Some unrelated instructions"}
    )
    calls, _ = await _run_deny_capturing_dispatch(db, tool_name=tool_name, error=error)
    assert calls == [], f"expected no callback for stand-alone executor, got {calls!r}"


@pytest.mark.asyncio
async def test_generic_tool_failure_skips_callback(
    db: aiosqlite.Connection,
) -> None:
    """An ordinary tool failure (e.g. an Edit with mismatched
    `old_string`, returning `is_error=True` with a non-deny message)
    must NOT trigger the callback. The sniffer keys on the two known
    deny signatures; everything else is left alone so the agent can
    react to the failure in-loop."""
    calls, _orch_id = await _run_deny_capturing_dispatch(
        db, tool_name="Edit", error="String to replace not found in file."
    )
    assert calls == [], f"non-deny error must not trigger callback: {calls!r}"


@pytest.mark.asyncio
async def test_deny_with_no_dispatcher_does_not_crash(
    db: aiosqlite.Connection,
) -> None:
    """Runner constructed without `prompt_dispatch` (today's tests,
    legacy callers) hits a deny → silent skip, turn completes
    cleanly. No log spam expected; the call site short-circuits before
    any DB lookup."""
    exec_id, _orch_id = await _ids(db)

    script = _deny_script(
        exec_id,
        tool_name="Write",
        error="[lockout] reader on /tmp.",
    )
    runner = SessionRunner(
        exec_id,
        ScriptedAgent(exec_id, scripts=[script]),
        db,
        # prompt_dispatch deliberately omitted.
    )
    # The assertion is "no crash" — `_run_one_turn` raising would fail.
    await _run_one_turn(runner)
