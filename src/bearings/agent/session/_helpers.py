"""Pure helper functions for the AgentSession package.

Free functions extracted from ``session.py`` (§FileSize). They have
no dependency on session state.
"""

from __future__ import annotations

import json
from typing import Any


def _pressure_hint_for(pct: float) -> str:
    """Band-specific steering text for the context-pressure block. At
    lower pressure we only nudge toward delegation; at higher pressure
    we add an explicit "consider checkpoint/fork" prompt so the model
    can raise it to the user without waiting for compaction to kick.
    Kept here (not in researcher_prompt.py) because the text is
    parent-side guidance and has nothing to do with the sub-agent's
    self-prompt."""
    if pct >= 85.0:
        return (
            "CRITICAL: auto-compact is close. Summarize current findings "
            "now, recommend the user fork from a recent checkpoint, and "
            "avoid any further broad codebase scans in this turn."
        )
    if pct >= 70.0:
        return (
            "High pressure. Prefer the `researcher` sub-agent via the "
            "Task tool for any further codebase survey work — its tool "
            "calls stay out of this context. Consider suggesting a "
            "checkpoint to the user before a large next turn."
        )
    return (
        "Elevated pressure. Prefer the `researcher` sub-agent via the "
        "Task tool for heavy tool work so its calls stay out of this "
        "context. Avoid re-reading files you have already read this "
        "session."
    )


def _stringify(content: str | list[dict[str, object]] | None) -> str | None:
    if content is None or isinstance(content, str):
        return content
    return json.dumps(content)


def _extract_tokens(usage: dict[str, Any] | None) -> dict[str, int | None]:
    """Pull the four token fields out of ``ResultMessage.usage``.

    The SDK forwards Anthropic's ``usage`` block verbatim, so the key
    shape is ``input_tokens``, ``output_tokens``,
    ``cache_creation_input_tokens``, ``cache_read_input_tokens`` (note
    the ``_input_tokens`` suffix on the cache fields). We normalize to
    the shorter column names used in the ``messages`` table.

    Missing keys stay None so the DB column stays NULL — useful for
    future SDK versions that might reshape the payload without us
    noticing. All four are ``None`` when ``usage`` itself is None
    (synthetic completions from stop/cancel paths).
    """
    if not usage:
        return {
            "input_tokens": None,
            "output_tokens": None,
            "cache_read_tokens": None,
            "cache_creation_tokens": None,
        }

    def _int_or_none(value: object) -> int | None:
        if isinstance(value, bool):
            # bool is a subclass of int; reject it explicitly so a
            # stray True doesn't silently become 1.
            return None
        if isinstance(value, int):
            return value
        return None

    return {
        "input_tokens": _int_or_none(usage.get("input_tokens")),
        "output_tokens": _int_or_none(usage.get("output_tokens")),
        "cache_read_tokens": _int_or_none(usage.get("cache_read_input_tokens")),
        "cache_creation_tokens": _int_or_none(usage.get("cache_creation_input_tokens")),
    }
