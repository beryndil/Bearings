"""History-priming + context-pressure rendering mixin.

:class:`_HistoryMixin` produces the first-turn history preamble (the
fallback for SDK-side ``resume=`` failures) and the per-turn
``<context-pressure>`` advisory injected ahead of the user prompt
when the last persisted percentage crosses
``_PRESSURE_INJECT_THRESHOLD_PCT``.

It also captures the SDK's per-turn context-usage snapshot so the
runner can persist the meter and emit a ``ContextUsage`` wire event.

Extracted from ``session.py`` (§FileSize); bodies unchanged.
"""

from __future__ import annotations

import aiosqlite
from claude_agent_sdk import ClaudeSDKClient, ClaudeSDKError

from bearings.agent.events import ContextUsage
from bearings.agent.session._constants import (
    _HISTORY_PRIME_MAX_CHARS,
    _HISTORY_PRIME_MAX_MESSAGES,
    _PRESSURE_INJECT_THRESHOLD_PCT,
)
from bearings.agent.session._helpers import _pressure_hint_for
from bearings.db._messages import list_messages


class _HistoryMixin:
    """AgentSession methods for history priming and context-pressure
    rendering."""

    # Type-only attribute declarations (populated by AgentSession.__init__).
    session_id: str
    db: aiosqlite.Connection | None
    model: str

    async def _build_history_prefix(self, prompt: str) -> str | None:
        """Render the last few DB-persisted turns into a preamble the
        SDK can prepend to the user's message.

        Why it exists: passing ``resume=<sdk_session_id>`` tells the
        CLI to rehydrate its own session file, but that path has
        failure modes we can't detect — the file may be gone, the
        cwd may have shifted, the system prompt may no longer match
        — and when it fails the fresh client simply starts with no
        history. This preamble gives the model an explicit textual
        transcript of recent turns as a guaranteed-present safety
        net.

        Called once per ``AgentSession`` instance (gated by
        ``_primed``). Returns ``None`` when there's nothing to prime
        (fresh session, no prior turns). The runner inserts the
        current user prompt into ``messages`` *before* calling
        ``stream()``, so the most-recent row is often this very
        turn's prompt — the dedupe logic below drops it so we don't
        echo the user's message back at them inside the preamble.
        """
        if self.db is None:
            return None
        # Pull one extra so the dedupe step still leaves the full
        # history window intact when the trailing row is our own.
        # `exclude_hidden=True` honors the `hidden_from_context` flag
        # (migration 0023) — rows the user marked as hidden skip the
        # history preamble so the next turn doesn't see them.
        rows = await list_messages(
            self.db,
            self.session_id,
            limit=_HISTORY_PRIME_MAX_MESSAGES + 1,
            exclude_hidden=True,
        )
        if not rows:
            return None
        # `list_messages(..., limit=...)` returns newest-first. Drop the
        # current turn's own user row if the runner already persisted it.
        if rows[0].get("role") == "user" and rows[0].get("content") == prompt:
            rows = rows[1:]
        if not rows:
            return None
        rows = rows[:_HISTORY_PRIME_MAX_MESSAGES]
        # Flip to oldest-first for a chronological transcript.
        rows.reverse()
        lines: list[str] = []
        for row in rows:
            role = str(row.get("role") or "unknown")
            body = str(row.get("content") or "")
            if len(body) > _HISTORY_PRIME_MAX_CHARS:
                body = body[:_HISTORY_PRIME_MAX_CHARS] + "…[truncated]"
            lines.append(f"{role}: {body}")
        if not lines:
            return None
        transcript = "\n\n".join(lines)
        return (
            "<previous-conversation>\n"
            "[The following are earlier turns in this session, provided "
            "so the assistant keeps context after a reconnect or process "
            "restart. Do not re-execute any tool calls shown below; use "
            "this only to understand the ongoing conversation.]\n\n"
            f"{transcript}\n\n"
            "[End of previous conversation. The user's new message "
            "follows.]\n"
            "</previous-conversation>\n\n"
        )

    async def _capture_context_usage(self, client: ClaudeSDKClient) -> ContextUsage | None:
        """Pull the SDK's current context-window snapshot and translate
        it into a ``ContextUsage`` wire event. Called inside the
        ``ClaudeSDKClient`` context manager at the end of a turn so the
        underlying CLI subprocess is still live — calling after
        ``async with`` exit would hit a closed connection.

        Best-effort: SDK call failure or response-shape mismatch
        returns None and the turn continues. The context meter is
        purely advisory — losing an update must not take down a
        successful turn. Swallowing errors here is the one place in
        this module where we accept a silent miss; everywhere else
        errors surface as ``ErrorEvent``.

        ``AttributeError`` covers the older-SDK case where the method
        isn't on the client at all (also matches test fixtures that
        skip stubbing it); ``ClaudeSDKError`` / ``OSError`` cover the
        active-call failure modes (CLI subprocess crash, transport
        hiccup)."""
        try:
            resp = await client.get_context_usage()
        except (ClaudeSDKError, OSError, AttributeError):
            return None

        def _opt_int(value: object) -> int | None:
            if isinstance(value, bool) or not isinstance(value, int):
                return None
            return value

        try:
            return ContextUsage(
                session_id=self.session_id,
                total_tokens=int(resp.get("totalTokens") or 0),
                max_tokens=int(resp.get("maxTokens") or 0),
                percentage=float(resp.get("percentage") or 0.0),
                model=str(resp.get("model") or self.model),
                is_auto_compact_enabled=bool(resp.get("isAutoCompactEnabled", False)),
                auto_compact_threshold=_opt_int(resp.get("autoCompactThreshold")),
            )
        except (TypeError, ValueError, AttributeError):
            return None

    async def _build_context_pressure_block(self) -> str | None:
        """Render a ``<context-pressure>`` block for injection ahead
        of the user's prompt when the last persisted pct crossed the
        threshold.

        Reads directly from the session row (populated by the runner
        on every ContextUsage event). Returns None on no-data or
        low-pressure — we only nag the model when there's real reason
        to, otherwise the advisory just eats tokens it's trying to
        save. Swallows DB errors: if the read fails the injection is
        silently skipped; the meter is advisory and the next turn
        still works."""
        if self.db is None:
            return None
        try:
            async with self.db.execute(
                "SELECT last_context_pct, last_context_tokens, last_context_max "
                "FROM sessions WHERE id = ?",
                (self.session_id,),
            ) as cursor:
                row = await cursor.fetchone()
        except aiosqlite.Error:
            return None
        if row is None or row["last_context_pct"] is None:
            return None
        pct = float(row["last_context_pct"])
        if pct < _PRESSURE_INJECT_THRESHOLD_PCT:
            return None
        tokens = row["last_context_tokens"]
        max_tokens = row["last_context_max"]
        hint = _pressure_hint_for(pct)
        return (
            f'<context-pressure pct="{pct:.1f}" tokens="{tokens}" '
            f'max="{max_tokens}">\n'
            f"{hint}\n"
            "</context-pressure>\n\n"
        )
