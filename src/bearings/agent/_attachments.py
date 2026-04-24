"""Token substitution for terminal-style `[File N]` attachments.

The composer inserts `[File 1]`, `[File 2]`, … tokens into the prompt
text alongside a sidecar list of `Attachment` objects carrying the real
absolute paths. Before the prompt hits the SDK we swap each referenced
token with its path (quoted if the path contains whitespace, so the
model sees one atom rather than two). The tokenised form is what we
persist in `messages.content`; the substituted form only ever lives as
an in-memory string on the runner's hot path.

This module is the single point of truth for the token shape. The
frontend mirrors the same regex in `frontend/src/lib/attachments.ts`;
keep the two in sync when the shape changes.
"""

from __future__ import annotations

import json
import re
from typing import Any

# `[File 1]` — literal `[File `, one-or-more digits, literal `]`. The
# digit group captures the attachment's `n`. Ordinary typed text like
# `[File Manager]` or `[file 1]` (lowercase) does NOT match, so a user
# who names an app or path with square brackets won't trigger a
# spurious substitution.
_ATTACHMENT_TOKEN = re.compile(r"\[File (\d+)\]")


def _quote_if_needed(path: str) -> str:
    """Wrap the path in double quotes iff it contains whitespace. The
    SDK reads the prompt as natural language, so unquoted spaces don't
    break parsing for the model itself — the quoting is defensive for
    downstream tools (slash-command arg splitters, shell invocations
    Claude might derive from the prompt) that tokenise on whitespace."""
    return f'"{path}"' if any(c.isspace() for c in path) else path


def substitute_tokens(prompt: str, attachments: list[dict[str, Any]]) -> str:
    """Replace each `[File N]` token in `prompt` with its absolute path.

    Tokens with no matching attachment entry are left as literal text —
    the user typed something that happened to match the shape and
    there's no mapping to substitute. Attachments whose `n` is not
    referenced in the prompt are silently ignored (the user inserted
    then deleted the token).
    """
    if not attachments:
        return prompt
    by_n = {int(a["n"]): a for a in attachments}

    def repl(match: re.Match[str]) -> str:
        n = int(match.group(1))
        entry = by_n.get(n)
        if entry is None:
            return match.group(0)
        return _quote_if_needed(str(entry["path"]))

    return _ATTACHMENT_TOKEN.sub(repl, prompt)


def referenced_ns(prompt: str) -> set[int]:
    """Return the set of `[File N]` numbers actually present in the
    prompt text. Used by the WS handler to drop attachments whose token
    the user removed before send — we don't want orphan metadata in the
    DB row, and we don't want to leak an upload path the user never
    referenced into the persisted transcript."""
    return {int(m.group(1)) for m in _ATTACHMENT_TOKEN.finditer(prompt)}


def prune_and_serialize(
    prompt: str, attachments: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], str | None]:
    """Filter `attachments` to only entries whose `n` still appears in
    `prompt`, and return `(pruned_list, json_for_db)`.

    The JSON string is what gets written to `messages.attachments`; it
    is None when the pruned list is empty so a user row with no
    attachments stays NULL in the column (matches the pre-0027 shape
    and keeps the storage honest).
    """
    if not attachments:
        return [], None
    active_ns = referenced_ns(prompt)
    pruned = [dict(a) for a in attachments if int(a["n"]) in active_ns]
    if not pruned:
        return [], None
    return pruned, json.dumps(pruned, separators=(",", ":"))
