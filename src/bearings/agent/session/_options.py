"""Per-turn option-building for ``AgentSession.stream()``.

Extracted from ``_stream_mixin.py`` so the streaming module fits the
§FileSize cap. ``build_stream_options`` returns the assembled
``ClaudeAgentOptions``, the prompt with history/pressure prefixes
applied, and the two side-channel queues used by the streaming bash
tool. Bodies unchanged from the original ``session.py``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    HookMatcher,
)

from bearings.agent.events import ToolOutputDelta
from bearings.agent.mcp_tools import (
    BEARINGS_MCP_SERVER_NAME,
    build_bearings_mcp_server,
)
from bearings.agent.prompt import assemble_prompt
from bearings.agent.researcher_prompt import RESEARCHER_PROMPT
from bearings.agent.session._constants import BASH_TOOL_SDK_NAME

if TYPE_CHECKING:
    from bearings.agent.session._stream_mixin import _StreamMixin

log = logging.getLogger(__name__)


async def build_stream_options(
    session: _StreamMixin,
    prompt: str,
) -> tuple[
    ClaudeAgentOptions,
    str,
    asyncio.Queue[ToolOutputDelta],
    asyncio.Queue[str],
]:
    """Assemble ``ClaudeAgentOptions`` and side-channel queues for a
    single ``stream()`` turn.

    Returns a 4-tuple of ``(options, prompt, delta_queue,
    pending_bash_ids)``. The prompt is returned with history-prime
    and context-pressure prefixes already applied so the caller can
    pass it directly to ``client.query``.
    """
    options_kwargs: dict[str, Any] = {
        "cwd": session.working_dir,
        "model": session.model,
        "include_partial_messages": True,
    }
    if session.max_budget_usd is not None:
        options_kwargs["max_budget_usd"] = session.max_budget_usd
    if session.permission_mode is not None:
        options_kwargs["permission_mode"] = session.permission_mode
    if session.sdk_session_id is not None:
        # Resume the prior SDK session so conversation history is on
        # the CLI side even though this is a fresh client.
        options_kwargs["resume"] = session.sdk_session_id
    if session.thinking is not None:
        options_kwargs["thinking"] = session.thinking
    if session.can_use_tool is not None:
        options_kwargs["can_use_tool"] = session.can_use_tool
    # Permission-profile gates. We pass each only when it diverges
    # from the SDK default so a power-user run (today's behavior)
    # still produces the exact same `ClaudeAgentOptions` payload as
    # before this knob landed.
    if session.setting_sources is not None:
        options_kwargs["setting_sources"] = session.setting_sources
    mcp_servers: dict[str, Any] = {}
    if not session.inherit_mcp_servers:
        # Empty dict tells the SDK "no MCP servers" rather than "use
        # defaults". The dict is required-typed in the SDK so we
        # can't pass `None`.
        options_kwargs["mcp_servers"] = mcp_servers
    # Per-stream side channels for the streaming bash tool.
    delta_queue: asyncio.Queue[ToolOutputDelta] = asyncio.Queue()
    pending_bash_ids: asyncio.Queue[str] = asyncio.Queue()

    def emit_delta_cb(tool_use_id: str, line: str) -> None:
        try:
            delta_queue.put_nowait(
                ToolOutputDelta(
                    session_id=session.session_id,
                    tool_call_id=tool_use_id,
                    delta=line,
                )
            )
        except asyncio.QueueFull:
            # Unbounded queue — should never happen. Log and drop
            # rather than crash the bash subprocess pump.
            log.warning(
                "session %s: delta_queue full (unexpected); dropping live frame",
                session.session_id,
            )

    # Bearings' own in-process MCP server. Gated by the
    # `enable_bearings_mcp` knob AND the presence of a DB (the
    # `get_tool_output` tool reads from it). Composed with the
    # `inherit_mcp_servers` behavior above — whatever the inherit
    # policy, the Bearings server is added on top.
    if session.enable_bearings_mcp and session.db is not None:
        # `working_dir_getter` is a closure (not a stored value) so
        # the dir_init tool resolves the current cwd at call time.
        # Closure form matches `db_getter` and keeps the MCP server
        # stateless on the session's mutable fields.
        mcp_servers[BEARINGS_MCP_SERVER_NAME] = build_bearings_mcp_server(
            session.session_id,
            session._current_db,
            emit_delta=emit_delta_cb,
            bash_id_getter=pending_bash_ids.get,
            working_dir_getter=lambda: session.working_dir,
        )
        options_kwargs["mcp_servers"] = mcp_servers
    hooks_map: dict[str, list[HookMatcher]] = {}
    if not session.inherit_hooks:
        options_kwargs["hooks"] = hooks_map
    # PostToolUse advisory hook (Option 6). Cheap to register even on
    # turns that don't produce big outputs — the hook short-circuits
    # on length.
    hooks_map.setdefault("PostToolUse", []).append(
        HookMatcher(hooks=[session._build_post_tool_use_hook()])
    )
    if session.enable_precompact_steering:
        hooks_map.setdefault("PreCompact", []).append(
            HookMatcher(hooks=[session._build_precompact_hook()])
        )
    if hooks_map:
        options_kwargs["hooks"] = hooks_map
    if session.enable_researcher_subagent:
        options_kwargs["agents"] = {
            "researcher": AgentDefinition(
                description=(
                    "Read-only codebase survey sub-agent. Runs tool "
                    "calls in isolated context and returns only a "
                    "compact summary — use it via the Task tool for "
                    "heavy exploration so raw outputs do not enter "
                    "this turn's context."
                ),
                prompt=RESEARCHER_PROMPT,
                # Streaming bash tool replaces the built-in Bash so
                # the researcher's shell calls also flow through the
                # live-output pipe. Read/Grep/Glob remain builtin —
                # they're already small-output.
                tools=["Read", "Grep", "Glob", BASH_TOOL_SDK_NAME],
                model="inherit",
            )
        }
    # Route the model away from the built-in `Bash` tool toward our
    # streaming MCP equivalent. We disallow built-in Bash and leave
    # allowed_tools empty (= "no allowlist filter") so every other
    # tool — including all MCP tools we expose — remains available.
    # Setting allowed_tools to a non-empty list would turn it into an
    # exclusive allowlist and accidentally hide everything else from
    # the model. Wired only when our MCP server is registered, so
    # test sessions without DB still have the built-in Bash available.
    if session.enable_bearings_mcp and session.db is not None:
        disallowed = list(options_kwargs.get("disallowed_tools") or [])
        if "Bash" not in disallowed:
            disallowed.append("Bash")
        options_kwargs["disallowed_tools"] = disallowed
    if session.db is not None:
        # Assemble the layered system prompt (base → tag memories →
        # session instructions) from the current DB state. Called per
        # turn so edits to tag memories / session instructions take
        # effect on the next prompt without restarting the WS.
        assembled = await assemble_prompt(session.db, session.session_id)
        options_kwargs["system_prompt"] = assembled.text
    options = ClaudeAgentOptions(**options_kwargs)
    # First-turn context priming. Only runs once per AgentSession
    # instance — subsequent turns rely on the SDK's own context
    # chain (the `resume=` hint above + the CLI's session file). Set
    # `_primed` before building the prefix so a transient DB error
    # below doesn't trap us in a re-prime loop; the worst case is a
    # single missed priming, not an infinite retry.
    if not session._primed:
        session._primed = True
        prefix = await session._build_history_prefix(prompt)
        if prefix is not None:
            prompt = prefix + prompt
    # Context-pressure injection (Option 1 finish). Runs on every
    # turn (not gated by `_primed`) because pressure accumulates over
    # the life of the session and we want the nudge every turn above
    # threshold, not just the first. The block is prepended after the
    # history prefix so the prompt reads:
    #   [transcript] [pressure] [user message]
    # — the model sees "here's where we are, here's the warning,
    # here's the ask."
    pressure_block = await session._build_context_pressure_block()
    if pressure_block is not None:
        prompt = pressure_block + prompt
    return options, prompt, delta_queue, pending_bash_ids
