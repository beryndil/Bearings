"""Module-wide constants for the AgentSession package.

Pulled out of ``session.py`` (§FileSize) so the values that govern
priming caps, pressure injection thresholds, and the precompact-hook
instruction text don't have to live in the same file as the heavy
``stream()`` body.
"""

from __future__ import annotations

from bearings.agent.mcp_tools import BEARINGS_MCP_SERVER_NAME

# Full SDK-prefixed name the model sees for our streaming bash tool.
# When session.stream() observes a ToolCallStart with this name it
# pushes the call's id onto the pending-bash-id queue so the bash
# handler can claim it on entry. See agent/bash_tool.py for the
# correlation rationale.
BASH_TOOL_SDK_NAME = f"mcp__{BEARINGS_MCP_SERVER_NAME}__bash"

# Upper bound on the number of recent DB messages pulled into the
# context-priming preamble on the first turn of a freshly-built
# AgentSession (see ``_build_history_prefix``). Ten messages is roughly
# the last five user/assistant exchanges, enough for "what were we just
# talking about?" without blowing the first-turn token budget.
_HISTORY_PRIME_MAX_MESSAGES = 10

# Per-message character cap for the priming preamble. Keeps the total
# preamble bounded (~20 KB ≈ 5k tokens worst case) even when a single
# assistant turn produced a long essay-style response. Messages longer
# than this are truncated with a visible "…[truncated]" marker so the
# model knows it's seeing a partial.
_HISTORY_PRIME_MAX_CHARS = 2000

# Context-pressure percentage at which the user-turn injection fires.
# Below this we stay silent — the meter already renders in the UI and
# nagging the model on every cheap turn burns its own attention budget.
# 50% is where ``get_context_usage()`` reports "yellow" band color; at
# that point a single research-heavy turn can tip us over the
# auto-compact threshold, so the advisory is worth the prompt real
# estate.
_PRESSURE_INJECT_THRESHOLD_PCT = 50.0

# Default per-turn tool-output cap used when ``AgentSession`` is built
# without one (tests, callers that don't care). Matches the default
# on ``AgentCfg.tool_output_cap_chars``. A dedicated module constant so
# the two places that have to agree can't drift.
_DEFAULT_TOOL_OUTPUT_CAP_CHARS = 8000

# Custom instructions handed to the CLI's compactor via the PreCompact
# hook. Goal: preserve the tool-dense research turns that today get
# lossy-summarized and force the user to re-run the research. The exact
# verbiage is important — the compactor is itself an LLM, so we speak
# to it plainly. Paired with the researcher sub-agent (Option 4 in
# the plan), this should make most research survive auto-compact.
_PRECOMPACT_CUSTOM_INSTRUCTIONS = (
    "Preserve VERBATIM on compaction: (1) the most recent assistant "
    "turn that issued more than ~5 tool calls and its tool outputs "
    "— these are research turns whose findings the user has not yet "
    "consumed; (2) any unanswered user question (a user turn followed "
    "by an assistant turn that did not address it); (3) any tool "
    "output whose findings have not yet been summarized in a "
    "subsequent assistant message. Drop aggressively: repeated Read() "
    "of the same path, failed Bash retries, tool outputs older than "
    "the most recent checkpoint, redundant reconnaissance of files "
    "that were then edited. Keep the user's original ask verbatim. "
    "When in doubt, preserve tool outputs over assistant prose — "
    "Bearings can always re-summarize prose, it cannot re-derive raw "
    "tool output without another API round-trip."
)
