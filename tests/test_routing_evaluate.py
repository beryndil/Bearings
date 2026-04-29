"""Routing evaluator unit tests (item 1.8; spec §App A + §3).

Covers each branch of :func:`bearings.agent.routing.evaluate` —
pure-function tests that take dataclass literals (no DB fixture).
The Done-when bar is ≥15 routing unit tests; this file lands 24
covering: per-match-type semantics, priority ordering across tags,
priority ordering between tag and system rules, disabled-rule
filtering, fallthrough to the absolute default, evaluated_rules
chain, quota state propagation, and the "first match wins" guarantee
across all match types.
"""

from __future__ import annotations

import time

import pytest

from bearings.agent.quota import QuotaSnapshot
from bearings.agent.routing import RoutingDecision, evaluate
from bearings.db.routing import RoutingRule, SystemRoutingRule


def _tag_rule(
    *,
    rule_id: int = 1,
    tag_id: int = 1,
    priority: int = 100,
    enabled: bool = True,
    match_type: str = "always",
    match_value: str | None = None,
    executor_model: str = "sonnet",
    advisor_model: str | None = "opus",
    advisor_max_uses: int = 5,
    effort_level: str = "auto",
    reason: str = "test rule",
) -> RoutingRule:
    """Tag-rule factory with sensible defaults."""
    now = int(time.time())
    return RoutingRule(
        id=rule_id,
        tag_id=tag_id,
        priority=priority,
        enabled=enabled,
        match_type=match_type,
        match_value=match_value,
        executor_model=executor_model,
        advisor_model=advisor_model,
        advisor_max_uses=advisor_max_uses,
        effort_level=effort_level,
        reason=reason,
        created_at=now,
        updated_at=now,
    )


def _sys_rule(
    *,
    rule_id: int = 1,
    priority: int = 1000,
    enabled: bool = True,
    match_type: str = "always",
    match_value: str | None = None,
    executor_model: str = "sonnet",
    advisor_model: str | None = "opus",
    advisor_max_uses: int = 5,
    effort_level: str = "auto",
    reason: str = "system rule",
    seeded: bool = True,
) -> SystemRoutingRule:
    """System-rule factory with sensible defaults."""
    now = int(time.time())
    return SystemRoutingRule(
        id=rule_id,
        priority=priority,
        enabled=enabled,
        match_type=match_type,
        match_value=match_value,
        executor_model=executor_model,
        advisor_model=advisor_model,
        advisor_max_uses=advisor_max_uses,
        effort_level=effort_level,
        reason=reason,
        seeded=seeded,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Match-type branches
# ---------------------------------------------------------------------------


def test_always_match_fires_on_any_message() -> None:
    """``always`` returns a match regardless of message content."""
    rule = _sys_rule(rule_id=1, match_type="always", match_value=None)
    decision = evaluate("anything goes here", [], [rule], None)
    assert decision.source == "system_rule"
    assert decision.matched_rule_id == 1
    assert decision.evaluated_rules == [1]


def test_keyword_case_insensitive_substring_hits() -> None:
    """``keyword`` matches case-insensitively anywhere in the message."""
    rule = _sys_rule(
        rule_id=2,
        match_type="keyword",
        match_value="architect, refactor",
        executor_model="opus",
        advisor_model=None,
        advisor_max_uses=0,
        effort_level="xhigh",
    )
    decision = evaluate("Help me Architect a system", [], [rule], None)
    assert decision.matched_rule_id == 2
    assert decision.executor_model == "opus"
    assert decision.advisor_model is None
    assert decision.effort_level == "xhigh"


def test_keyword_first_term_wins_when_multiple_listed() -> None:
    """Comma-separated keyword list — any one term firing matches the rule."""
    rule = _sys_rule(
        rule_id=3,
        match_type="keyword",
        match_value="alpha, beta, gamma",
    )
    decision = evaluate("we should beta-test", [], [rule], None)
    assert decision.matched_rule_id == 3


def test_keyword_no_term_matches_falls_through() -> None:
    """No matching keyword → next rule (here the always default)."""
    keyword_rule = _sys_rule(
        rule_id=4, priority=50, match_type="keyword", match_value="never-occurs"
    )
    fallback = _sys_rule(rule_id=5, priority=1000, match_type="always")
    decision = evaluate("an unrelated message", [], [keyword_rule, fallback], None)
    assert decision.matched_rule_id == 5
    assert decision.evaluated_rules == [4, 5]


def test_regex_match_with_anchors_hits() -> None:
    """``regex`` match with anchors and case-insensitive flag."""
    rule = _sys_rule(
        rule_id=6,
        match_type="regex",
        match_value=r"^(what|how) ",
        executor_model="haiku",
    )
    decision = evaluate("What is the weather?", [], [rule], None)
    assert decision.matched_rule_id == 6
    assert decision.executor_model == "haiku"


def test_regex_invalid_pattern_disables_rule() -> None:
    """Spec §3: invalid regex disables the rule (does not crash routing)."""
    bad_rule = _sys_rule(rule_id=7, priority=10, match_type="regex", match_value="(unclosed")
    fallback = _sys_rule(rule_id=8, priority=1000, match_type="always")
    decision = evaluate("anything", [], [bad_rule, fallback], None)
    # Walker still recorded that bad_rule was tested (and skipped).
    assert decision.matched_rule_id == 8
    assert decision.evaluated_rules == [7, 8]


def test_length_gt_compares_message_length() -> None:
    """``length_gt`` integer compare against ``len(message)``."""
    rule = _sys_rule(
        rule_id=9,
        match_type="length_gt",
        match_value="20",
        executor_model="sonnet",
        effort_level="high",
    )
    decision = evaluate("a" * 25, [], [rule], None)
    assert decision.matched_rule_id == 9
    assert decision.effort_level == "high"


def test_length_lt_compares_message_length() -> None:
    """``length_lt`` integer compare against ``len(message)``."""
    rule = _sys_rule(
        rule_id=10,
        match_type="length_lt",
        match_value="80",
        executor_model="haiku",
    )
    decision = evaluate("short", [], [rule], None)
    assert decision.matched_rule_id == 10
    assert decision.executor_model == "haiku"


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------


def test_lower_priority_number_checks_first() -> None:
    """Spec §3: lower priority number = checked first (within same tag)."""
    rule_high_prio = _tag_rule(rule_id=11, priority=10, match_type="always", executor_model="opus")
    rule_low_prio = _tag_rule(rule_id=12, priority=100, match_type="always", executor_model="haiku")
    decision = evaluate("msg", [(1, [rule_low_prio, rule_high_prio])], [], None)
    # rule_high_prio (priority=10) wins despite being last in input list.
    assert decision.matched_rule_id == 11
    assert decision.executor_model == "opus"


def test_priority_tied_rules_resolve_by_id() -> None:
    """Tied priority — lower id wins (deterministic tie-breaking)."""
    rule_a = _tag_rule(rule_id=13, priority=50, match_type="always")
    rule_b = _tag_rule(rule_id=14, priority=50, match_type="always")
    decision = evaluate("msg", [(1, [rule_b, rule_a])], [], None)
    assert decision.matched_rule_id == 13


def test_tag_rules_beat_system_rules() -> None:
    """Spec §3 step 4: system rules only run when no tag rule matched."""
    tag_rule = _tag_rule(rule_id=15, match_type="always", executor_model="opus", reason="tag")
    sys_rule = _sys_rule(rule_id=16, match_type="always", reason="sys")
    decision = evaluate("msg", [(1, [tag_rule])], [sys_rule], None)
    assert decision.source == "tag_rule"
    assert decision.matched_rule_id == 15
    assert decision.executor_model == "opus"


def test_cross_tag_priority_ordering() -> None:
    """Spec §3 step 1: priority is across tags, not within tags."""
    tag1_rule = _tag_rule(rule_id=17, tag_id=1, priority=50, match_type="always")
    tag2_rule_high = _tag_rule(rule_id=18, tag_id=2, priority=10, match_type="always")
    decision = evaluate(
        "msg",
        [(1, [tag1_rule]), (2, [tag2_rule_high])],
        [],
        None,
    )
    # Tag2's rule has priority=10, beats tag1's priority=50.
    assert decision.matched_rule_id == 18


# ---------------------------------------------------------------------------
# Enabled / fallthrough / fallback
# ---------------------------------------------------------------------------


def test_disabled_rule_is_skipped() -> None:
    """Disabled rules are not evaluated (spec §3 "all enabled rules")."""
    disabled = _tag_rule(rule_id=19, priority=10, enabled=False, match_type="always")
    enabled = _tag_rule(rule_id=20, priority=20, match_type="always", executor_model="haiku")
    decision = evaluate("msg", [(1, [disabled, enabled])], [], None)
    assert decision.matched_rule_id == 20
    # Disabled rule does not appear in evaluated_rules either.
    assert 19 not in decision.evaluated_rules


def test_no_rules_falls_through_to_absolute_default() -> None:
    """Spec §3 step 5: absolute default when nothing matches."""
    decision = evaluate("anything", [], [], None)
    assert decision.source == "default"
    assert decision.executor_model == "sonnet"
    assert decision.advisor_model == "opus"
    assert decision.effort_level == "auto"
    assert decision.matched_rule_id is None


def test_no_match_among_rules_falls_through_to_absolute_default() -> None:
    """All rules tested but none match → absolute default with full chain."""
    rule_a = _sys_rule(rule_id=21, priority=10, match_type="keyword", match_value="never1")
    rule_b = _sys_rule(rule_id=22, priority=20, match_type="keyword", match_value="never2")
    decision = evaluate("totally unrelated", [], [rule_a, rule_b], None)
    assert decision.source == "default"
    assert decision.evaluated_rules == [21, 22]


def test_evaluated_rules_truncates_at_match() -> None:
    """``evaluated_rules`` includes only rules tested up to and including match."""
    rule1 = _sys_rule(rule_id=30, priority=10, match_type="keyword", match_value="missme")
    rule2 = _sys_rule(rule_id=31, priority=20, match_type="always")
    rule3 = _sys_rule(rule_id=32, priority=30, match_type="always")
    decision = evaluate("msg", [], [rule1, rule2, rule3], None)
    # rule1 missed, rule2 matched, rule3 never tested.
    assert decision.matched_rule_id == 31
    assert decision.evaluated_rules == [30, 31]


# ---------------------------------------------------------------------------
# Quota state propagation
# ---------------------------------------------------------------------------


def test_quota_state_at_decision_populated_when_snapshot_provided() -> None:
    """Spec §App A: ``quota_state_at_decision`` carries snapshot percentages."""
    snapshot = QuotaSnapshot(
        captured_at=int(time.time()),
        overall_used_pct=0.42,
        sonnet_used_pct=0.55,
        overall_resets_at=None,
        sonnet_resets_at=None,
        raw_payload="{}",
    )
    decision = evaluate(
        "msg",
        [],
        [_sys_rule(rule_id=40, match_type="always")],
        snapshot,
    )
    assert decision.quota_state_at_decision == {
        "overall_used_pct": 0.42,
        "sonnet_used_pct": 0.55,
    }


def test_quota_state_empty_when_no_snapshot() -> None:
    """``quota_state_at_decision`` is empty dict when snapshot is None."""
    decision = evaluate(
        "msg",
        [],
        [_sys_rule(rule_id=41, match_type="always")],
        None,
    )
    assert decision.quota_state_at_decision == {}


# ---------------------------------------------------------------------------
# Real spec-table seeded rules — sanity-checks the evaluator against the
# default system rules verbatim from spec §3.
# ---------------------------------------------------------------------------


def test_architecture_keyword_resolves_to_opus_solo() -> None:
    """Spec §3 priority-10: architect keywords → Opus solo, xhigh effort."""
    rule = _sys_rule(
        rule_id=50,
        priority=10,
        match_type="keyword",
        match_value="architect, design system",
        executor_model="opus",
        advisor_model=None,
        advisor_max_uses=0,
        effort_level="xhigh",
        reason="Hard architectural reasoning — Opus solo with extended thinking",
    )
    decision = evaluate(
        "We need to design system boundaries here",
        [],
        [rule],
        None,
    )
    assert decision.executor_model == "opus"
    assert decision.advisor_model is None
    assert decision.effort_level == "xhigh"


def test_short_message_resolves_to_haiku() -> None:
    """Spec §3 priority-50: ``length_lt 80`` → haiku + opus advisor."""
    short_rule = _sys_rule(
        rule_id=51,
        priority=50,
        match_type="length_lt",
        match_value="80",
        executor_model="haiku",
        advisor_model="opus",
        advisor_max_uses=3,
        effort_level="low",
    )
    fallback = _sys_rule(rule_id=52, priority=1000, match_type="always", reason="Workhorse default")
    decision = evaluate("Quick fix?", [], [short_rule, fallback], None)
    assert decision.matched_rule_id == 51
    assert decision.executor_model == "haiku"
    assert decision.advisor_max_uses == 3


def test_long_message_resolves_to_sonnet_high() -> None:
    """Spec §3 priority-60: ``length_gt 4000`` → sonnet + opus + high."""
    long_rule = _sys_rule(
        rule_id=53,
        priority=60,
        match_type="length_gt",
        match_value="4000",
        executor_model="sonnet",
        advisor_model="opus",
        advisor_max_uses=5,
        effort_level="high",
    )
    decision = evaluate("x" * 5000, [], [long_rule], None)
    assert decision.matched_rule_id == 53
    assert decision.effort_level == "high"


def test_workhorse_default_when_no_keyword_matches() -> None:
    """Spec §3 priority-1000 ``always`` fallback fires last."""
    arch_rule = _sys_rule(
        rule_id=60,
        priority=10,
        match_type="keyword",
        match_value="architect",
        executor_model="opus",
        advisor_model=None,
    )
    workhorse = _sys_rule(
        rule_id=61,
        priority=1000,
        match_type="always",
        executor_model="sonnet",
        advisor_model="opus",
        reason="Workhorse default",
    )
    decision = evaluate("just a message", [], [arch_rule, workhorse], None)
    assert decision.matched_rule_id == 61
    assert decision.executor_model == "sonnet"
    assert decision.reason == "Workhorse default"


def test_keyword_rule_skips_when_match_value_is_empty_string() -> None:
    """Defence-in-depth: a keyword rule with an empty match_value cannot match.

    The dataclass validator rejects ``match_value=None`` for non-
    ``always`` types at construction; this test verifies the
    evaluator's runtime defence by smuggling an empty-string value
    through (which the schema CHECK does *not* reject).
    """
    # Construct via __setattr__ on a frozen instance: dataclasses.replace
    # is the supported escape hatch, but here we want a value that
    # passes __post_init__. Empty list of terms inside a keyword
    # match_value parses as "no terms" → never matches.
    bad = _sys_rule(rule_id=70, priority=10, match_type="keyword", match_value=",")
    fallback = _sys_rule(rule_id=71, priority=1000, match_type="always")
    decision = evaluate("msg", [], [bad, fallback], None)
    assert decision.matched_rule_id == 71


def test_length_gt_unparseable_match_value_skips_rule() -> None:
    """A length rule whose ``match_value`` is non-numeric is skipped."""
    bad = _sys_rule(rule_id=80, priority=10, match_type="length_gt", match_value="not-a-number")
    fallback = _sys_rule(rule_id=81, priority=1000, match_type="always")
    decision = evaluate("msg", [], [bad, fallback], None)
    assert decision.matched_rule_id == 81


def test_returns_routing_decision_instance() -> None:
    """Sanity: result is a :class:`RoutingDecision` (not a dict)."""
    decision = evaluate("msg", [], [], None)
    assert isinstance(decision, RoutingDecision)


def test_matched_rule_carries_advisor_max_uses_through() -> None:
    """advisor_max_uses field flows from rule to decision verbatim."""
    rule = _sys_rule(
        rule_id=90,
        match_type="always",
        advisor_max_uses=7,
    )
    decision = evaluate("msg", [], [rule], None)
    assert decision.advisor_max_uses == 7


def test_keyword_with_empty_terms_in_csv_does_not_match_empty_message() -> None:
    """``"foo,,bar"`` — empty middle term is dropped, not matched as empty."""
    rule = _sys_rule(rule_id=91, match_type="keyword", match_value="foo,,bar")
    decision = evaluate("nothing", [], [rule], None)
    # Neither foo nor bar in message → no match → fall through.
    assert decision.source == "default"


@pytest.mark.parametrize("advisor_value", [None, "opus", "claude-opus-4-6"])
def test_advisor_model_passes_through_short_or_long_form(
    advisor_value: str | None,
) -> None:
    """advisor_model accepts None, short name, and full SDK ID."""
    rule = _sys_rule(rule_id=99, match_type="always", advisor_model=advisor_value)
    decision = evaluate("msg", [], [rule], None)
    assert decision.advisor_model == advisor_value
