"""Override-rate aggregator — spec §8 + §10 "Rules to review".

For each routing rule (tag rule + system rule) the aggregator
computes a rolling 14-day override rate:

```
override_rate = (sessions where user manually changed executor or advisor before send) /
                (sessions where this rule fired)
```

Rules with ``override_rate > 0.30`` (per
:data:`bearings.config.constants.OVERRIDE_RATE_REVIEW_THRESHOLD`) are
surfaced in the routing rule editor as "Review:" highlighted rows
(spec §10 + §8 "Override-rate calculation").

Per ``docs/architecture-v1.md`` §1.1.4 + §4 the aggregator is a
domain class colocated with the routing-feature pure functions. It
reads message rows directly via the connection because the
aggregation is a single GROUP BY and creating a separate db/ helper
would just push the same SQL one layer down.

Public surface:

* :class:`OverrideRate` — frozen result row carrying counts + rate.
* :class:`OverrideAggregator` — class wrapping the connection +
  config (window_days, threshold). Single :meth:`compute` method
  returns a list of :class:`OverrideRate` for every rule the
  message corpus references.

Pure-vs-impure boundary:

* :class:`OverrideAggregator` is impure (it reads the messages
  table). Its :meth:`compute` is the only impure method.
* :func:`compute_rates_from_counts` is the pure helper that turns
  per-rule counts into :class:`OverrideRate` rows; tested without
  the DB.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import aiosqlite

from bearings.config.constants import (
    OVERRIDE_RATE_REVIEW_THRESHOLD,
    OVERRIDE_RATE_WINDOW_DAYS,
)


@dataclass(frozen=True)
class OverrideRate:
    """Spec §8 per-rule override-rate row.

    Field semantics:

    * ``rule_kind`` — ``"tag_rule"`` or ``"system_rule"``; mirrors the
      ``RoutingDecision.source`` value the rule produced.
    * ``rule_id`` — the matching ``tag_routing_rules.id`` or
      ``system_routing_rules.id``.
    * ``fired_count`` — number of sessions in-window where this rule
      was the chosen rule. The denominator.
    * ``overridden_count`` — number of those sessions whose first
      assistant message lands with ``routing_source = 'manual'`` or
      ``'manual_override_quota'``. The numerator. (Spec §8: "user
      manually changed executor or advisor before send.")
    * ``rate`` — ``overridden_count / fired_count``, or 0.0 if
      ``fired_count == 0``.
    * ``review`` — convenience flag, ``rate >
      :data:`bearings.config.constants.OVERRIDE_RATE_REVIEW_THRESHOLD```.
    """

    rule_kind: str
    rule_id: int
    fired_count: int
    overridden_count: int
    rate: float
    review: bool

    def __post_init__(self) -> None:
        if self.rule_kind not in {"tag_rule", "system_rule"}:
            raise ValueError(
                f"OverrideRate.rule_kind must be 'tag_rule' or 'system_rule' "
                f"(got {self.rule_kind!r})"
            )
        if self.fired_count < 0:
            raise ValueError(f"OverrideRate.fired_count must be ≥ 0 (got {self.fired_count})")
        if self.overridden_count < 0:
            raise ValueError(
                f"OverrideRate.overridden_count must be ≥ 0 (got {self.overridden_count})"
            )
        if self.overridden_count > self.fired_count:
            raise ValueError(
                f"OverrideRate.overridden_count ({self.overridden_count}) cannot "
                f"exceed fired_count ({self.fired_count})"
            )
        if not 0.0 <= self.rate <= 1.0:
            raise ValueError(f"OverrideRate.rate must be in [0.0, 1.0] (got {self.rate})")


def compute_rates_from_counts(
    *,
    fire_counts: dict[tuple[str, int], int],
    override_counts: dict[tuple[str, int], int],
    threshold: float = OVERRIDE_RATE_REVIEW_THRESHOLD,
) -> list[OverrideRate]:
    """Pure helper — turn per-rule fire/override counts into result rows.

    Both input dicts key on ``(rule_kind, rule_id)``. Rules in
    ``override_counts`` but not ``fire_counts`` are dropped (a manual
    override on a rule that never fired in-window is impossible —
    such a row would have a non-zero override against a zero
    denominator).

    Result rows are sorted by ``(rule_kind, rule_id)`` so the API
    surface is deterministic across invocations.
    """
    out: list[OverrideRate] = []
    for key in sorted(fire_counts.keys()):
        fired = fire_counts[key]
        overridden = override_counts.get(key, 0)
        if fired == 0:
            # Skip — rule didn't fire in-window. The pure helper
            # tolerates the input shape; the caller's SQL ensures
            # ``fired > 0`` for every key, but the defensive branch
            # keeps the helper safe to reuse.
            continue
        rate = overridden / fired
        out.append(
            OverrideRate(
                rule_kind=key[0],
                rule_id=key[1],
                fired_count=fired,
                overridden_count=overridden,
                rate=rate,
                review=rate > threshold,
            )
        )
    return out


class OverrideAggregator:
    """14-day per-rule override-rate computer (spec §8 + §10).

    The aggregator reads ``messages`` rows directly. Per spec §5
    every persisted message carries ``routing_source`` and
    ``matched_rule_id`` (item 1.9 wires the per-message persistence;
    until then aggregation runs against whatever rows item-1.7's
    placeholder has produced — which is fine, the aggregator just
    sees zero rule fires and returns an empty list).

    Construction:

        aggregator = OverrideAggregator(
            connection,
            window_days=OVERRIDE_RATE_WINDOW_DAYS,
            threshold=OVERRIDE_RATE_REVIEW_THRESHOLD,
        )
        rows = await aggregator.compute()

    Per-tag and per-rule slicing live as separate methods on the
    same class so the API surface (spec §9 ``GET
    /api/usage/override_rates?days=14``) can request a custom window
    without reconstructing the aggregator.
    """

    def __init__(
        self,
        connection: aiosqlite.Connection,
        *,
        window_days: int = OVERRIDE_RATE_WINDOW_DAYS,
        threshold: float = OVERRIDE_RATE_REVIEW_THRESHOLD,
    ) -> None:
        if window_days <= 0:
            raise ValueError(f"OverrideAggregator.window_days must be > 0 (got {window_days})")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                f"OverrideAggregator.threshold must be in [0.0, 1.0] (got {threshold})"
            )
        self._connection = connection
        self._window_days = window_days
        self._threshold = threshold

    @property
    def window_days(self) -> int:
        """The rolling-window length in days."""
        return self._window_days

    @property
    def threshold(self) -> float:
        """The "Review:" highlighting cutoff."""
        return self._threshold

    async def compute(self) -> list[OverrideRate]:
        """Return per-rule :class:`OverrideRate` rows for the rolling window.

        Aggregation strategy:

        1. ``messages.created_at`` is a TEXT ISO-8601 timestamp per the
           ``messages`` schema (item 1.7+). The cutoff is computed as
           ``utcnow() - window_days`` and compared lexicographically —
           ISO-8601-with-offset sorts identically to chronological
           order, so a string compare is correct here.
        2. Group by ``(routing_source, matched_rule_id)`` (the
           message tracks which rule fired); count rows where
           ``routing_source IN ('tag_rule', 'system_rule')`` for fires
           and ``routing_source IN ('manual', 'manual_override_quota')``
           for overrides — but the override join needs the rule id
           that *would* have fired, which is captured at session
           creation on the *session's* first assistant message.
        3. The simplest correct approach: count session-creation
           assistant messages by ``(routing_source, matched_rule_id)``,
           then for each session whose final routing_source ended in a
           manual variant, attribute the override to whatever rule
           fired at session-creation. Item 1.9's per-message
           persistence captures both; until then the aggregator reads
           whichever rows exist.

        For v1 the aggregator implements (3) with a single GROUP BY
        on the messages table — every session-creation row stamps
        ``matched_rule_id`` (when a rule fired) and
        ``routing_source``. The override counter increments when a
        session whose original creation row pointed at rule R has any
        message in-window with ``routing_source IN ('manual',
        'manual_override_quota')``. The query below does this in two
        passes (fired counts; override counts via a subquery joining
        sessions back to their creation rule) so each session is
        attributed to at most one rule.
        """
        cutoff_unix = int(time.time()) - self._window_days * 86_400
        # The messages table uses ISO-8601 TEXT timestamps. SQLite's
        # ``strftime('%s', t)`` returns the unix-seconds form so we
        # can compare numerically without converting in Python.
        cutoff_arg = str(cutoff_unix)
        fire_counts: dict[tuple[str, int], int] = {}
        override_counts: dict[tuple[str, int], int] = {}

        # Pass 1: fired counts. Group all messages with a routing
        # source naming a rule by (source, matched_rule_id); count
        # distinct sessions because spec §8 "sessions where this rule
        # fired" is a session-level metric.
        cursor = await self._connection.execute(
            "SELECT routing_source, matched_rule_id, COUNT(DISTINCT session_id) "
            "FROM messages WHERE matched_rule_id IS NOT NULL "
            "AND routing_source IN ('tag_rule', 'system_rule') "
            "AND CAST(strftime('%s', created_at) AS INTEGER) >= ? "
            "GROUP BY routing_source, matched_rule_id",
            (cutoff_arg,),
        )
        try:
            rows = await cursor.fetchall()
        finally:
            await cursor.close()
        for row in rows:
            kind = str(row[0])
            rule_id = int(str(row[1]))
            count = int(str(row[2]))
            fire_counts[(kind, rule_id)] = count

        # Pass 2: override counts. For each session that has at least
        # one message in-window with a manual routing source, take the
        # rule the session originally fired with (the earliest
        # message's matched_rule_id). The subquery picks that earliest
        # row; the outer GROUP BY counts how many of those sessions
        # had a manual override anywhere in-window.
        cursor = await self._connection.execute(
            "WITH origin AS ( "
            "  SELECT m.session_id, m.routing_source AS origin_source, "
            "         m.matched_rule_id AS origin_rule_id "
            "  FROM messages m "
            "  WHERE m.id = ( "
            "    SELECT id FROM messages "
            "    WHERE session_id = m.session_id "
            "    AND matched_rule_id IS NOT NULL "
            "    ORDER BY created_at ASC LIMIT 1 "
            "  ) "
            "  AND m.matched_rule_id IS NOT NULL "
            "  AND m.routing_source IN ('tag_rule', 'system_rule') "
            "), overrides AS ( "
            "  SELECT DISTINCT session_id FROM messages "
            "  WHERE routing_source IN ('manual', 'manual_override_quota') "
            "  AND CAST(strftime('%s', created_at) AS INTEGER) >= ? "
            ") "
            "SELECT origin.origin_source, origin.origin_rule_id, COUNT(*) "
            "FROM origin INNER JOIN overrides USING (session_id) "
            "GROUP BY origin.origin_source, origin.origin_rule_id",
            (cutoff_arg,),
        )
        try:
            rows = await cursor.fetchall()
        finally:
            await cursor.close()
        for row in rows:
            kind = str(row[0])
            rule_id = int(str(row[1]))
            count = int(str(row[2]))
            override_counts[(kind, rule_id)] = count

        return compute_rates_from_counts(
            fire_counts=fire_counts,
            override_counts=override_counts,
            threshold=self._threshold,
        )

    async def review_rules(self) -> list[OverrideRate]:
        """Convenience: subset of :meth:`compute` where ``review is True``.

        The "Rules to review" widget in the inspector (spec §10) reads
        this list directly.
        """
        all_rates = await self.compute()
        return [r for r in all_rates if r.review]


__all__ = [
    "OverrideAggregator",
    "OverrideRate",
    "compute_rates_from_counts",
]
