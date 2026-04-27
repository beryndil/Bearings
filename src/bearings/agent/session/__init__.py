"""Public API re-exports for the AgentSession package.

The original ``session.py`` was split into a package on 2026-04-27
to honor §FileSize (≤400 lines per file). External consumers continue
to import via ``bearings.agent.session``::

    from bearings.agent.session import AgentSession

Tests also reach into a few module-private names (``_extract_tokens``,
``_HISTORY_PRIME_MAX_CHARS``) — those continue to be importable here
for API stability.

Internal layout:

- ``_constants`` — module-wide constants (history prime caps, pressure
  threshold, default tool-output cap, precompact instructions,
  ``BASH_TOOL_SDK_NAME``).
- ``_helpers`` — pure free functions: ``_pressure_hint_for``,
  ``_stringify``, ``_extract_tokens``.
- ``_history_mixin`` — ``_HistoryMixin``: history-prefix and
  context-pressure rendering.
- ``_hooks_mixin`` — ``_HooksMixin``: PostToolUse / PreCompact hook
  builders.
- ``_events_mixin`` — ``_EventsMixin``: stream-event and block
  translators (``_translate_stream_event``, ``_translate_block``,
  ``_tool_call_end``).
- ``_stream_mixin`` — ``_StreamMixin``: the per-turn ``stream()``
  generator.
- ``core`` — :class:`AgentSession` itself (init/setters/interrupt),
  multi-inheriting the four mixins.
"""

from __future__ import annotations

# ClaudeSDKClient is re-exported here (and bound BEFORE the AgentSession
# import below) so existing tests that monkeypatch
# ``bearings.agent.session.ClaudeSDKClient`` still take effect: the
# stream loop in :mod:`_stream_mixin` resolves the symbol via this
# package's namespace at call time. Re-binding it here is the entire
# reason for the explicit rebind. Removing this attribute breaks the
# entire test suite for AgentSession-driven scenarios.
from claude_agent_sdk import ClaudeSDKClient

from bearings.agent.session._constants import (
    _DEFAULT_TOOL_OUTPUT_CAP_CHARS,
    _HISTORY_PRIME_MAX_CHARS,
    _HISTORY_PRIME_MAX_MESSAGES,
    _PRECOMPACT_CUSTOM_INSTRUCTIONS,
    _PRESSURE_INJECT_THRESHOLD_PCT,
    BASH_TOOL_SDK_NAME,
)
from bearings.agent.session._helpers import (
    _extract_tokens,
    _pressure_hint_for,
    _stringify,
)
from bearings.agent.session.core import AgentSession

__all__ = [
    "AgentSession",
    "BASH_TOOL_SDK_NAME",
    "ClaudeSDKClient",
    # Internal names re-exported for tests that exercised them
    # directly when this module was a single file. Keep them
    # importable so the test suite continues to compile.
    "_DEFAULT_TOOL_OUTPUT_CAP_CHARS",
    "_HISTORY_PRIME_MAX_CHARS",
    "_HISTORY_PRIME_MAX_MESSAGES",
    "_PRECOMPACT_CUSTOM_INSTRUCTIONS",
    "_PRESSURE_INJECT_THRESHOLD_PCT",
    "_extract_tokens",
    "_pressure_hint_for",
    "_stringify",
]
