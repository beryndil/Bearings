"""The :class:`AgentSession` class itself.

Owns the constructor, the simple per-attribute setters, and
``interrupt()``. Per-turn behavior lives in the four sibling mixins;
this class composes them and adds the bookkeeping that the rest of
Bearings interacts with directly (the WS handler, the runner, the
checklist driver runtime).

Multi-inheritance order matters at runtime: the three "real-impl"
mixins (``_HistoryMixin`` / ``_HooksMixin`` / ``_EventsMixin``) come
BEFORE ``_StreamMixin`` so MRO resolves real implementations before
the type-only stubs that ``_StreamMixin`` declares for cross-mixin
``self.X`` access.
"""

from __future__ import annotations

import aiosqlite
from claude_agent_sdk import (
    CanUseTool,
    ClaudeSDKClient,
    ClaudeSDKError,
    PermissionMode,
    ThinkingConfig,
)

from bearings.agent.session._constants import _DEFAULT_TOOL_OUTPUT_CAP_CHARS
from bearings.agent.session._events_mixin import _EventsMixin
from bearings.agent.session._history_mixin import _HistoryMixin
from bearings.agent.session._hooks_mixin import _HooksMixin
from bearings.agent.session._stream_mixin import _StreamMixin


class AgentSession(_HistoryMixin, _HooksMixin, _EventsMixin, _StreamMixin):
    """Wraps a single Claude Code agent session via claude-agent-sdk.

    One instance per WebSocket connection; a short-lived
    ``ClaudeSDKClient`` is created for each ``stream()`` call.
    """

    def __init__(
        self,
        session_id: str,
        working_dir: str,
        model: str,
        max_budget_usd: float | None = None,
        db: aiosqlite.Connection | None = None,
        sdk_session_id: str | None = None,
        permission_mode: PermissionMode | None = None,
        thinking: ThinkingConfig | None = None,
        setting_sources: list[str] | None = None,
        inherit_mcp_servers: bool = True,
        inherit_hooks: bool = True,
        tool_output_cap_chars: int = _DEFAULT_TOOL_OUTPUT_CAP_CHARS,
        enable_bearings_mcp: bool = True,
        enable_precompact_steering: bool = True,
        enable_researcher_subagent: bool = False,
    ) -> None:
        self.session_id = session_id
        self.working_dir = working_dir
        self.model = model
        self.max_budget_usd = max_budget_usd
        # Extended-thinking config passed through to
        # `ClaudeAgentOptions.thinking`. When set, the SDK adds the
        # corresponding `--thinking` / `--max-thinking-tokens` flag to
        # the CLI invocation and the model emits ThinkingBlocks / live
        # thinking deltas, which we surface as `Thinking` wire events
        # for the Conversation view's collapsed thinking block.
        self.thinking = thinking
        # Optional DB connection for the v0.2 prompt assembler. When
        # set, `stream()` calls `assemble_prompt` and passes the
        # concatenated layered prompt as `system_prompt`. Unit tests
        # that don't exercise persistence can leave it None; the WS
        # handler wires it in production.
        self.db = db
        # Claude-agent-sdk session id captured from the first
        # AssistantMessage and passed back as `resume=` on the next
        # turn so the fresh SDK client inherits prior history instead
        # of starting blind. WS handler persists this to `sessions.
        # sdk_session_id` so reconnects keep context too.
        self.sdk_session_id = sdk_session_id
        # Current permission mode — applied to every subsequent
        # stream() call's options. Flipping this (via
        # set_permission_mode) is how `/plan` engages plan mode.
        self.permission_mode = permission_mode
        # Permission-profile gates wired through to the SDK. `None` /
        # `True` reproduce today's behavior — the SDK applies its own
        # defaults (inherit user `~/.claude` settings, MCP servers,
        # hooks). The `safe` profile flips these so a session under
        # Bearings starts from a clean slate without leaking the
        # operator's global config into the session run. See
        # `bearings.config.AgentCfg` for the per-knob rationale.
        self.setting_sources = setting_sources
        self.inherit_mcp_servers = inherit_mcp_servers
        self.inherit_hooks = inherit_hooks
        # Optional `can_use_tool` callback passed to `ClaudeAgentOptions`.
        # When set (by the runner, post-construction), the SDK invokes
        # it whenever a tool call needs permission — the runner parks
        # a Future and fans an `ApprovalRequest` event out to WS
        # subscribers, resolving the Future when the UI replies. Left
        # None for unit tests that don't exercise permission gating.
        self.can_use_tool: CanUseTool | None = None
        # Tracks the currently-active SDK client so `interrupt()` can
        # reach into an in-flight stream. Set inside `stream()` under
        # the `async with`; cleared on exit.
        self._client: ClaudeSDKClient | None = None
        # Whether this instance has already primed the SDK with a
        # transcript of recent history. Set True after the first
        # `stream()` call so subsequent turns rely on `resume=` /
        # SDK-side context instead of re-prepending the same history.
        # A brand-new runner after a reconnect starts with
        # `_primed=False`, so the first turn carries an explicit
        # preamble — a belt-and-suspenders backup for cases where SDK
        # session resume fails silently (stale session file, cwd
        # mismatch, system_prompt divergence). See `_build_history_prefix`.
        self._primed: bool = False
        # Per-turn tool-output cap. When a tool output is larger than
        # this (in chars) the PostToolUse hook appends a short
        # advisory to the model's context telling it the full text is
        # persisted in the Bearings DB and retrievable via the
        # `bearings__get_tool_output` MCP tool. See plan Option 6.
        self.tool_output_cap_chars = tool_output_cap_chars
        # Feature toggles — all four default to the values that
        # reproduce the token-cost plan's recommended shipping state.
        # Tests that want to lock a specific subset of these on/off
        # can pass them explicitly.
        self.enable_bearings_mcp = enable_bearings_mcp
        self.enable_precompact_steering = enable_precompact_steering
        self.enable_researcher_subagent = enable_researcher_subagent

    def set_permission_mode(self, mode: PermissionMode | None) -> None:
        self.permission_mode = mode

    def _current_db(self) -> aiosqlite.Connection | None:
        """DB-getter closure handed to the Bearings MCP server so its
        tool handlers always see the session's current connection even
        if it swaps under us. Kept as a bound method so subclassing
        stays straightforward."""
        return self.db

    async def interrupt(self) -> None:
        """Cancel an in-flight stream at the SDK level. When a tool is
        mid-execution this tells the Claude CLI to abort it rather
        than merely stopping the token stream. A no-op when no stream
        is active."""
        client = self._client
        if client is None:
            return
        try:
            await client.interrupt()
        except (ClaudeSDKError, OSError):
            # The SDK may refuse a second interrupt or fail if the
            # subprocess is already winding down. Swallow — the outer
            # WS handler breaks out of the stream loop regardless.
            pass
