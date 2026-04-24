"""Unit tests for the `[File N]` token substitution helpers that feed
the runner's composer→SDK boundary. These functions are pure, so they
don't need the test DB or runner fixtures — the tests live close to
the helper module and exercise the edge cases the runner relies on:
preservation of tokenised content, pruning of orphaned sidecar entries,
and the quoting rule for whitespace-bearing paths.

Also covers the `MessageOut` attachments-decoder: the DB column stores
JSON as a string, Pydantic can't coerce that into `list[Attachment]`
by default, so the model carries a `@field_validator` that pre-parses.
Exercised here because the round-trip (store → MessageOut) is the
user-facing contract and the decoder's edge cases (None, empty, list
passed through, malformed JSON) are easy to regress.
"""

from __future__ import annotations

import json

from bearings.agent._attachments import (
    prune_and_serialize,
    referenced_ns,
    substitute_tokens,
)
from bearings.api.models import MessageOut


def test_substitute_tokens_swaps_each_reference() -> None:
    """Each `[File N]` is replaced with the matching path; order and
    surrounding text are preserved exactly. The happy path — what
    every clean composer submit looks like."""
    prompt = "look at [File 1] and compare with [File 2]"
    attachments = [
        {"n": 1, "path": "/uploads/a/one.log", "filename": "one.log", "size_bytes": 10},
        {"n": 2, "path": "/uploads/b/two.log", "filename": "two.log", "size_bytes": 20},
    ]
    result = substitute_tokens(prompt, attachments)
    assert result == "look at /uploads/a/one.log and compare with /uploads/b/two.log"


def test_substitute_tokens_quotes_paths_with_whitespace() -> None:
    """Whitespace in the path gets double-quoted so downstream tools
    that tokenise on whitespace (slash-command arg parsers, derived
    shell calls) see one atom. Claude itself reads it as plain natural
    language either way — the quoting is defensive."""
    prompt = "open [File 1]"
    attachments = [
        {"n": 1, "path": "/tmp/has space/file.txt", "filename": "file.txt", "size_bytes": 1},
    ]
    assert substitute_tokens(prompt, attachments) == 'open "/tmp/has space/file.txt"'


def test_substitute_tokens_leaves_literal_matches_alone() -> None:
    """`[File 9]` with no matching attachment stays literal. The user
    typed something that happened to match the shape; substituting an
    arbitrary path would be wrong, and the alternative of erroring
    would break every prompt that mentions the token as text."""
    prompt = "the CLI prints [File 9] in its help"
    attachments = [{"n": 1, "path": "/a", "filename": "a", "size_bytes": 1}]
    assert substitute_tokens(prompt, attachments) == "the CLI prints [File 9] in its help"


def test_substitute_tokens_is_case_sensitive_and_tight() -> None:
    """`[file 1]` (lowercase) and `[File Manager]` are NOT tokens —
    the regex requires the literal `[File ` prefix and a digit-only
    body. This keeps unrelated bracketed phrases from silently
    mutating into paths."""
    prompt = "the [file 1] and [File Manager] should survive"
    attachments = [{"n": 1, "path": "/x", "filename": "x", "size_bytes": 1}]
    assert substitute_tokens(prompt, attachments) == prompt


def test_substitute_tokens_no_op_without_attachments() -> None:
    """Empty sidecar returns the prompt unchanged — hot-path shortcut
    matters because every attachment-free submit hits this branch."""
    assert substitute_tokens("no files here", []) == "no files here"


def test_referenced_ns_returns_set_of_token_numbers() -> None:
    """`referenced_ns` is the scanner `prune_and_serialize` uses to
    decide which sidecar entries to keep. Multiple refs of the same
    token collapse (set semantics); non-matching text contributes
    nothing."""
    assert referenced_ns("nothing here") == set()
    assert referenced_ns("only [File 3]") == {3}
    assert referenced_ns("[File 1] and [File 1] and [File 2]") == {1, 2}


def test_prune_and_serialize_drops_orphan_attachments() -> None:
    """The user dropped two files but only kept `[File 1]` in the
    text (deleted the second token before send). The pruned list
    contains only entry 1, and the JSON string that hits the DB is
    compact (no spaces) so the column stays tidy."""
    prompt = "use [File 1] for this"
    attachments = [
        {"n": 1, "path": "/a", "filename": "a", "size_bytes": 1},
        {"n": 2, "path": "/b", "filename": "b", "size_bytes": 2},
    ]
    pruned, payload = prune_and_serialize(prompt, attachments)
    assert len(pruned) == 1
    assert pruned[0]["n"] == 1
    assert payload is not None
    # Round-trip equality check — the JSON in the column must parse
    # back to the pruned list.
    assert json.loads(payload) == pruned


def test_prune_and_serialize_returns_null_payload_for_empty_text() -> None:
    """When no tokens survive in the text (user deleted every
    attachment reference before sending), we drop the sidecar to None
    so the DB column stays NULL — the row shouldn't claim attachments
    that aren't actually in the message."""
    prompt = "never mind, forget the files"
    attachments = [{"n": 1, "path": "/a", "filename": "a", "size_bytes": 1}]
    pruned, payload = prune_and_serialize(prompt, attachments)
    assert pruned == []
    assert payload is None


def test_prune_and_serialize_noop_for_empty_input() -> None:
    """No sidecar at all short-circuits — this is the hot path for
    every plain-text submit, so it must never build a JSON payload."""
    pruned, payload = prune_and_serialize("hi there", [])
    assert pruned == []
    assert payload is None


def _message_kwargs(**overrides: object) -> dict[str, object]:
    """Minimal kwargs set for constructing a MessageOut; individual
    tests override `attachments`."""
    base: dict[str, object] = {
        "id": "m1",
        "session_id": "s1",
        "role": "user",
        "content": "hi",
        "created_at": "2026-04-23T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_messageout_decodes_json_string_attachments() -> None:
    """The DB path hands `MessageOut(**row)` a dict whose
    `attachments` key is a JSON string. The validator parses it into
    a list, so the wire representation is the structured shape clients
    expect without routes having to pre-decode."""
    payload = '[{"n":1,"path":"/uploads/a/one.log","filename":"one.log","size_bytes":10}]'
    msg = MessageOut(**_message_kwargs(attachments=payload))
    assert msg.attachments is not None
    assert len(msg.attachments) == 1
    assert msg.attachments[0].path == "/uploads/a/one.log"
    assert msg.attachments[0].n == 1


def test_messageout_accepts_list_attachments_passthrough() -> None:
    """Non-string values (already decoded list, or None) flow through
    untouched. Matters for in-memory constructors in tests and for any
    future route that assembles MessageOut without going through the
    DB column."""
    structured = [
        {"n": 1, "path": "/a", "filename": "a", "size_bytes": 1},
    ]
    msg = MessageOut(**_message_kwargs(attachments=structured))
    assert msg.attachments is not None
    assert msg.attachments[0].filename == "a"


def test_messageout_empty_string_and_null_are_none() -> None:
    """NULL DB column and an empty string both serialise as None —
    the transcript renderer treats missing/null as "no attachments"
    and an empty-but-present value would be a lie about the row."""
    assert MessageOut(**_message_kwargs(attachments=None)).attachments is None
    assert MessageOut(**_message_kwargs(attachments="")).attachments is None


def test_messageout_malformed_json_degrades_to_none() -> None:
    """A corrupt `attachments` row (hand-edited DB, failed migration)
    must not crash MessageOut construction — the rest of the message
    is still valid content and the transcript should render without
    the chips rather than 500 the list endpoint."""
    msg = MessageOut(**_message_kwargs(attachments="{not: json"))
    assert msg.attachments is None


def test_messageout_roundtrips_json_from_helper() -> None:
    """End-to-end check: what `prune_and_serialize` writes to the DB
    decodes back through MessageOut to an equivalent structured list.
    The two sides of the feature have to agree on the JSON shape."""
    attachments = [
        {"n": 1, "path": "/a", "filename": "a.log", "size_bytes": 5},
        {"n": 2, "path": "/b", "filename": "b.log", "size_bytes": 7},
    ]
    _, payload = prune_and_serialize("[File 1] [File 2]", attachments)
    assert payload is not None
    msg = MessageOut(**_message_kwargs(attachments=payload))
    assert msg.attachments is not None
    assert [a.model_dump() for a in msg.attachments] == json.loads(payload)
