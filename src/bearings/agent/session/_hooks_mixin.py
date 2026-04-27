"""PostToolUse / PreCompact hook builder mixin for ``AgentSession``.

Extracted from ``session.py`` (§FileSize); bodies unchanged.
"""

from __future__ import annotations

from typing import Any

from bearings.agent.mcp_tools import tool_output_char_len
from bearings.agent.session._constants import _PRECOMPACT_CUSTOM_INSTRUCTIONS


class _HooksMixin:
    """AgentSession methods that build SDK hook callbacks."""

    # Type-only attribute declarations (populated by AgentSession.__init__).
    tool_output_cap_chars: int

    def _build_post_tool_use_hook(self) -> Any:
        """Return an async hook callback that attaches a tool-output
        retrieval advisory when a tool produced more than
        ``tool_output_cap_chars`` of content.

        The advisory is the best we can do for native (Read / Bash /
        Grep / Edit) tools: the SDK's hook output schema only allows
        rewriting MCP tool output (``updatedMCPToolOutput``), not
        native tool output. So we leave the raw output in context for
        this turn but tell the model "this is big — when it gets
        dropped from context on compaction, retrieve via
        ``bearings__get_tool_output`` instead of asking me to re-run
        the tool." That steers the model toward summarizing
        aggressively in its reply and relying on retrieval later.

        Returns a no-op callback (``None`` output) when the cap is
        non-positive — lets operators disable the advisory without
        unwiring the hook machinery."""
        cap = int(self.tool_output_cap_chars or 0)

        async def hook(
            input_data: Any,
            tool_use_id: str | None,
            _context: Any,
        ) -> dict[str, Any]:
            if cap <= 0:
                return {}
            response = input_data.get("tool_response") if isinstance(input_data, dict) else None
            body: Any
            if isinstance(response, dict):
                body = response.get("content")
            else:
                body = response
            try:
                length = await tool_output_char_len(body)
            except (TypeError, ValueError):
                length = 0
            if length <= cap:
                return {}
            tool_name = input_data.get("tool_name") if isinstance(input_data, dict) else None
            advisory = (
                f"[bearings: this {tool_name or 'tool'} call produced "
                f"{length} chars of output — above the {cap}-char "
                "context-cost cap. Summarize now; on future turns, if "
                "the raw text has fallen out of context, retrieve via "
                "`bearings__get_tool_output` with "
                f'tool_use_id="{tool_use_id or "<id>"}" rather than '
                "re-running the tool.]"
            )
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": advisory,
                }
            }

        return hook

    def _build_precompact_hook(self) -> Any:
        """Return an async hook callback that hands the CLI's
        compactor explicit preservation instructions. See
        ``_PRECOMPACT_CUSTOM_INSTRUCTIONS`` for the policy text."""

        async def hook(
            _input_data: Any,
            _tool_use_id: str | None,
            _context: Any,
        ) -> dict[str, Any]:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreCompact",
                    "customInstructions": _PRECOMPACT_CUSTOM_INSTRUCTIONS,
                }
            }

        return hook
