"""Override aggregator unit tests (item 1.8; spec §8 + §10).

Covers :func:`bearings.agent.override_aggregator.compute_rates_from_counts`
(pure helper) and :class:`bearings.agent.override_aggregator.OverrideAggregator`
(impure DB-bound aggregator) including 14-day window edge cases and
the "Review:" threshold trigger.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest

from bearings.agent.override_aggregator import (
    OverrideAggregator,
    OverrideRate,
    compute_rates_from_counts,
)
from bearings.config.constants import OVERRIDE_RATE_REVIEW_THRESHOLD
from bearings.db.connection import load_schema


@pytest.fixture
async def conn(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    db_path = tmp_path / "override.db"
    connection = await aiosqlite.connect(db_path)
    try:
        await load_schema(connection)
        yield connection
    finally:
        await connection.close()


# ---------------------------------------------------------------------------
# Pure-helper tests
# ---------------------------------------------------------------------------


def test_compute_zero_overrides_yields_zero_rate() -> None:
    """No overrides → rate 0.0 → review False."""
    rates = compute_rates_from_counts(
        fire_counts={("system_rule", 1): 10},
        override_counts={},
    )
    assert rates == [
        OverrideRate(
            rule_kind="system_rule",
            rule_id=1,
            fired_count=10,
            overridden_count=0,
            rate=0.0,
            review=False,
        )
    ]


def test_compute_below_threshold_does_not_trigger_review() -> None:
    """rate ≤ 0.30 → review False."""
    rates = compute_rates_from_counts(
        fire_counts={("system_rule", 1): 10},
        override_counts={("system_rule", 1): 3},  # rate=0.30, NOT > 0.30
    )
    assert rates[0].rate == pytest.approx(0.30)
    assert rates[0].review is False


def test_compute_above_threshold_triggers_review() -> None:
    """rate > 0.30 → review True (spec §8 cutoff)."""
    rates = compute_rates_from_counts(
        fire_counts={("system_rule", 5): 10},
        override_counts={("system_rule", 5): 4},  # rate=0.40
    )
    assert rates[0].rate == pytest.approx(0.40)
    assert rates[0].review is True


def test_compute_uses_constant_threshold_by_default() -> None:
    """Default threshold matches the constants module."""
    # 31% on a 100-fire denominator → review True iff threshold == 0.30.
    rates = compute_rates_from_counts(
        fire_counts={("system_rule", 7): 100},
        override_counts={("system_rule", 7): 31},
    )
    assert rates[0].review is True
    assert pytest.approx(0.30) == OVERRIDE_RATE_REVIEW_THRESHOLD


def test_compute_skips_zero_fire_count_keys() -> None:
    """A rule with 0 fires is not surfaced (would be a 0/0 rate)."""
    rates = compute_rates_from_counts(
        fire_counts={("system_rule", 1): 0},
        override_counts={("system_rule", 1): 0},
    )
    assert rates == []


def test_compute_orders_results_deterministically() -> None:
    """Output sorted by ``(rule_kind, rule_id)``."""
    rates = compute_rates_from_counts(
        fire_counts={
            ("tag_rule", 5): 10,
            ("system_rule", 2): 10,
            ("tag_rule", 1): 10,
        },
        override_counts={},
    )
    assert [(r.rule_kind, r.rule_id) for r in rates] == [
        ("system_rule", 2),
        ("tag_rule", 1),
        ("tag_rule", 5),
    ]


def test_override_rate_rejects_overridden_exceeding_fired() -> None:
    """Validation: overridden_count cannot exceed fired_count."""
    with pytest.raises(ValueError, match="cannot"):
        OverrideRate(
            rule_kind="tag_rule",
            rule_id=1,
            fired_count=5,
            overridden_count=10,
            rate=0.5,
            review=False,
        )


def test_override_rate_rejects_unknown_kind() -> None:
    """Validation: rule_kind alphabet enforced."""
    with pytest.raises(ValueError, match="rule_kind"):
        OverrideRate(
            rule_kind="bogus",
            rule_id=1,
            fired_count=1,
            overridden_count=0,
            rate=0.0,
            review=False,
        )


# ---------------------------------------------------------------------------
# Impure (DB-bound) tests
# ---------------------------------------------------------------------------


async def _seed_session(conn: aiosqlite.Connection, session_id: str) -> None:
    """Seed a chat session row so message FK is satisfied."""
    iso = time.strftime("%Y-%m-%dT%H:%M:%S.000000+00:00", time.gmtime())
    await conn.execute(
        "INSERT INTO sessions (id, kind, title, working_dir, model, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, "chat", "test", "/tmp", "sonnet", iso, iso),
    )


async def _seed_message(
    conn: aiosqlite.Connection,
    *,
    session_id: str,
    routing_source: str | None,
    matched_rule_id: int | None,
    age_days: float = 0.0,
) -> None:
    """Seed a message row with given routing source + rule + age in days."""
    age_seconds = int(age_days * 86_400)
    iso = time.strftime(
        "%Y-%m-%dT%H:%M:%S.000000+00:00",
        time.gmtime(time.time() - age_seconds),
    )
    msg_id = f"msg_{session_id}_{routing_source or 'none'}_{matched_rule_id}_{age_days}"
    await conn.execute(
        "INSERT INTO messages (id, session_id, role, content, "
        "matched_rule_id, routing_source, created_at) "
        "VALUES (?, ?, 'assistant', '', ?, ?, ?)",
        (msg_id, session_id, matched_rule_id, routing_source, iso),
    )


async def test_aggregator_empty_db_returns_empty_list(
    conn: aiosqlite.Connection,
) -> None:
    """No messages → no rates."""
    aggregator = OverrideAggregator(conn)
    result = await aggregator.compute()
    assert result == []


async def test_aggregator_counts_in_window_session_fires(
    conn: aiosqlite.Connection,
) -> None:
    """A recent rule fire surfaces with fired_count=1."""
    await _seed_session(conn, "s1")
    await _seed_message(
        conn,
        session_id="s1",
        routing_source="system_rule",
        matched_rule_id=42,
    )
    await conn.commit()
    rates = await OverrideAggregator(conn).compute()
    assert len(rates) == 1
    assert rates[0].rule_id == 42
    assert rates[0].fired_count == 1
    assert rates[0].overridden_count == 0


async def test_aggregator_excludes_outside_window_messages(
    conn: aiosqlite.Connection,
) -> None:
    """A message outside the rolling window is not counted."""
    await _seed_session(conn, "s1")
    await _seed_message(
        conn,
        session_id="s1",
        routing_source="system_rule",
        matched_rule_id=99,
        age_days=20.0,  # outside 14d window
    )
    await conn.commit()
    rates = await OverrideAggregator(conn, window_days=14).compute()
    assert rates == []


async def test_aggregator_counts_overrides_against_origin_rule(
    conn: aiosqlite.Connection,
) -> None:
    """Session's earliest rule fire + later manual override → counted."""
    await _seed_session(conn, "s1")
    await _seed_message(
        conn,
        session_id="s1",
        routing_source="system_rule",
        matched_rule_id=7,
        age_days=1.0,
    )
    await _seed_message(
        conn,
        session_id="s1",
        routing_source="manual",
        matched_rule_id=None,
        age_days=0.5,
    )
    await conn.commit()
    rates = await OverrideAggregator(conn).compute()
    assert len(rates) == 1
    assert rates[0].rule_id == 7
    assert rates[0].fired_count == 1
    assert rates[0].overridden_count == 1
    assert rates[0].rate == pytest.approx(1.0)
    assert rates[0].review is True


async def test_aggregator_review_rules_filters_to_review_subset(
    conn: aiosqlite.Connection,
) -> None:
    """``review_rules`` returns only rates above the threshold."""
    await _seed_session(conn, "s1")
    await _seed_session(conn, "s2")
    # Two sessions both fired rule 11; only s1 has a manual override.
    await _seed_message(
        conn,
        session_id="s1",
        routing_source="system_rule",
        matched_rule_id=11,
    )
    await _seed_message(
        conn,
        session_id="s1",
        routing_source="manual_override_quota",
        matched_rule_id=None,
    )
    await _seed_message(
        conn,
        session_id="s2",
        routing_source="system_rule",
        matched_rule_id=11,
    )
    await conn.commit()
    aggregator = OverrideAggregator(conn)
    review = await aggregator.review_rules()
    # 1/2 = 50% > 30% → review True.
    assert len(review) == 1
    assert review[0].rule_id == 11
    assert review[0].rate == pytest.approx(0.5)


async def test_aggregator_rejects_zero_window(
    conn: aiosqlite.Connection,
) -> None:
    """Construction-time validation: window must be > 0."""
    with pytest.raises(ValueError, match="window_days"):
        OverrideAggregator(conn, window_days=0)


async def test_aggregator_rejects_out_of_range_threshold(
    conn: aiosqlite.Connection,
) -> None:
    """Construction-time validation: threshold must be in [0, 1]."""
    with pytest.raises(ValueError, match="threshold"):
        OverrideAggregator(conn, threshold=1.5)
