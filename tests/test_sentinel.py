"""Unit tests for ``bearings.agent.sentinel``.

Verifies the wire-format parsing rules from
``docs/behavior/checklists.md`` §"Sentinels (auto-pause / failure /
completion)" — the six sentinel kinds, malformed-block ignoring,
multiple-sentinels-per-message ordering, and the terminal-vs-followup
classification.
"""

from __future__ import annotations

import pytest

from bearings.agent.sentinel import SentinelFinding, first_terminal, parse
from bearings.config.constants import (
    ITEM_OUTCOME_BLOCKED,
    ITEM_OUTCOME_FAILED,
    ITEM_OUTCOME_SKIPPED,
    SENTINEL_KIND_FOLLOWUP_BLOCKING,
    SENTINEL_KIND_FOLLOWUP_NONBLOCKING,
    SENTINEL_KIND_HANDOFF,
    SENTINEL_KIND_ITEM_BLOCKED,
    SENTINEL_KIND_ITEM_DONE,
    SENTINEL_KIND_ITEM_FAILED,
)


def test_parse_empty_returns_empty() -> None:
    assert parse("") == []


def test_parse_self_closing_item_done() -> None:
    findings = parse('hello <bearings:sentinel kind="item_done" /> world')
    assert len(findings) == 1
    assert findings[0].kind == SENTINEL_KIND_ITEM_DONE


def test_parse_handoff_with_plug() -> None:
    body = (
        'before <bearings:sentinel kind="handoff">'
        "<plug>continue from here</plug>"
        "</bearings:sentinel> after"
    )
    findings = parse(body)
    assert len(findings) == 1
    assert findings[0].kind == SENTINEL_KIND_HANDOFF
    assert findings[0].plug == "continue from here"


def test_parse_handoff_with_empty_plug() -> None:
    body = '<bearings:sentinel kind="handoff"></bearings:sentinel>'
    findings = parse(body)
    assert len(findings) == 1
    assert findings[0].plug == ""


def test_parse_followup_blocking_requires_label() -> None:
    body = (
        '<bearings:sentinel kind="followup_blocking">'
        "<label>do this child first</label>"
        "</bearings:sentinel>"
    )
    findings = parse(body)
    assert len(findings) == 1
    assert findings[0].kind == SENTINEL_KIND_FOLLOWUP_BLOCKING
    assert findings[0].label == "do this child first"


def test_parse_followup_blocking_without_label_is_ignored() -> None:
    body = '<bearings:sentinel kind="followup_blocking"></bearings:sentinel>'
    findings = parse(body)
    assert findings == []


def test_parse_followup_nonblocking() -> None:
    body = '<bearings:sentinel kind="followup_nonblocking"><label>later</label></bearings:sentinel>'
    findings = parse(body)
    assert len(findings) == 1
    assert findings[0].kind == SENTINEL_KIND_FOLLOWUP_NONBLOCKING
    assert findings[0].label == "later"


def test_parse_item_blocked_default_category() -> None:
    body = (
        '<bearings:sentinel kind="item_blocked"><text>need credentials</text></bearings:sentinel>'
    )
    findings = parse(body)
    assert len(findings) == 1
    assert findings[0].kind == SENTINEL_KIND_ITEM_BLOCKED
    assert findings[0].category == ITEM_OUTCOME_BLOCKED
    assert findings[0].reason == "need credentials"


def test_parse_item_blocked_with_explicit_category() -> None:
    body = (
        '<bearings:sentinel kind="item_blocked">'
        f"<category>{ITEM_OUTCOME_SKIPPED}</category>"
        "<text>not applicable</text></bearings:sentinel>"
    )
    findings = parse(body)
    assert len(findings) == 1
    assert findings[0].category == ITEM_OUTCOME_SKIPPED


def test_parse_item_blocked_rejects_unknown_category() -> None:
    body = (
        '<bearings:sentinel kind="item_blocked">'
        "<category>not-a-real-category</category></bearings:sentinel>"
    )
    findings = parse(body)
    assert findings == []


def test_parse_item_failed_with_reason() -> None:
    body = '<bearings:sentinel kind="item_failed"><reason>tests broke</reason></bearings:sentinel>'
    findings = parse(body)
    assert len(findings) == 1
    assert findings[0].kind == SENTINEL_KIND_ITEM_FAILED
    assert findings[0].reason == "tests broke"


def test_parse_unknown_kind_ignored() -> None:
    body = '<bearings:sentinel kind="not_a_real_kind" />'
    assert parse(body) == []


def test_parse_self_closing_only_for_item_done() -> None:
    # handoff requires payload; self-closing form is not legal for it
    body = '<bearings:sentinel kind="handoff" />'
    assert parse(body) == []


def test_parse_multiple_sentinels_in_order() -> None:
    body = (
        '<bearings:sentinel kind="followup_nonblocking">'
        "<label>a</label></bearings:sentinel>\n"
        '<bearings:sentinel kind="item_done" />'
    )
    findings = parse(body)
    assert [f.kind for f in findings] == [
        SENTINEL_KIND_FOLLOWUP_NONBLOCKING,
        SENTINEL_KIND_ITEM_DONE,
    ]


def test_parse_handoff_multi_line_plug() -> None:
    body = """
<bearings:sentinel kind="handoff">
<plug>
multi-line
plug body
</plug>
</bearings:sentinel>
""".strip()
    findings = parse(body)
    assert len(findings) == 1
    assert "multi-line" in (findings[0].plug or "")
    assert "plug body" in (findings[0].plug or "")


def test_parse_incomplete_open_tag_ignored() -> None:
    # No closing tag → DOTALL non-greedy still won't match
    body = '<bearings:sentinel kind="handoff"><plug>hi'
    assert parse(body) == []


def test_first_terminal_picks_terminal_kinds() -> None:
    findings = [
        SentinelFinding(kind=SENTINEL_KIND_FOLLOWUP_NONBLOCKING, label="x"),
        SentinelFinding(kind=SENTINEL_KIND_ITEM_DONE),
        SentinelFinding(kind=SENTINEL_KIND_ITEM_FAILED, reason="r"),
    ]
    terminal = first_terminal(findings)
    assert terminal is not None
    assert terminal.kind == SENTINEL_KIND_ITEM_DONE


def test_first_terminal_returns_none_when_only_followups() -> None:
    findings = [
        SentinelFinding(kind=SENTINEL_KIND_FOLLOWUP_BLOCKING, label="x"),
        SentinelFinding(kind=SENTINEL_KIND_FOLLOWUP_NONBLOCKING, label="y"),
    ]
    assert first_terminal(findings) is None


def test_first_terminal_handoff_is_terminal() -> None:
    findings = [SentinelFinding(kind=SENTINEL_KIND_HANDOFF, plug="x")]
    terminal = first_terminal(findings)
    assert terminal is not None
    assert terminal.kind == SENTINEL_KIND_HANDOFF


def test_sentinel_finding_validates_kind() -> None:
    with pytest.raises(ValueError, match="kind"):
        SentinelFinding(kind="not-real")


def test_sentinel_finding_validates_category() -> None:
    with pytest.raises(ValueError, match="category"):
        SentinelFinding(kind=SENTINEL_KIND_ITEM_BLOCKED, category="bogus")


def test_parse_item_failed_with_known_outcomes_match_constants() -> None:
    """Smoke: every constant in the outcome alphabet is treatable."""
    # Each known outcome category should produce a valid finding when
    # placed inside item_blocked.
    for category in (ITEM_OUTCOME_BLOCKED, ITEM_OUTCOME_FAILED, ITEM_OUTCOME_SKIPPED):
        body = (
            f'<bearings:sentinel kind="item_blocked">'
            f"<category>{category}</category></bearings:sentinel>"
        )
        findings = parse(body)
        assert len(findings) == 1
        assert findings[0].category == category
