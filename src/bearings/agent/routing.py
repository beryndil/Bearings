"""Routing-decision dataclass (spec §App A — verbatim shape).

This module lays down the immutable :class:`RoutingDecision` carrier
that :class:`bearings.agent.session.SessionConfig` embeds (per arch
§4.8). The pure ``evaluate(message, tags_with_rules, system_rules,
quota_snapshot) -> RoutingDecision`` function plus the
``apply_quota_guard`` companion are out of scope for item 1.1; arch
§1.1.4 places them in this same module, and item 1.8 lands them
alongside this dataclass.

Validation lives in :meth:`RoutingDecision.__post_init__`. The set of
acceptable ``executor_model`` short names, ``effort_level`` labels, and
``source`` enum values are pulled from
:mod:`bearings.config.constants` per the item-0.5 "no inline literals"
gate. Long-form SDK model IDs (e.g. ``claude-sonnet-4-5``) are accepted
via the
:data:`bearings.config.constants.EXECUTOR_MODEL_FULL_ID_PREFIX` test —
the SDK resolves the long-form on its own, so the validator's job is to
catch typos like ``"sonet"`` or ``"oppus"`` at construction time
without enumerating every future model ID.

References:

* ``docs/model-routing-v1-spec.md`` §App A — frozen dataclass shape.
* ``docs/architecture-v1.md`` §4.1 — the same shape repeated as the
  arch-doc handoff to the implementer.
* ``docs/architecture-v1.md`` §4.8 — :class:`SessionConfig` embedding.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bearings.config.constants import (
    EXECUTOR_MODEL_FULL_ID_PREFIX,
    KNOWN_EFFORT_LEVELS,
    KNOWN_EXECUTOR_MODELS,
    KNOWN_ROUTING_SOURCES,
)


@dataclass(frozen=True)
class RoutingDecision:
    """Spec §App A — the immutable result of a routing evaluation.

    Field semantics are spec-verbatim (see also arch §4.1):

    * ``executor_model`` — short-name from
      :data:`bearings.config.constants.KNOWN_EXECUTOR_MODELS` or a full
      SDK model ID (any string starting with ``claude-``).
    * ``advisor_model`` — short-name or full ID; ``None`` means no
      advisor on this turn.
    * ``advisor_max_uses`` — 0-to-N. Per spec §App A "ignored if
      ``advisor_model`` is None"; this validator allows 0 with a non-
      ``None`` advisor model (means "advisor declared but disabled
      this turn") so the routing layer can carry rule-table defaults
      through unchanged.
    * ``effort_level`` — one of
      :data:`bearings.config.constants.KNOWN_EFFORT_LEVELS`. The
      translation to SDK ``effort`` literal is owned by
      ``agent/options.py:build_options`` (item 1.2) via
      :data:`bearings.config.constants.EFFORT_LEVEL_TO_SDK`.
    * ``source`` — one of
      :data:`bearings.config.constants.KNOWN_ROUTING_SOURCES`.
    * ``reason`` — free-text, surfaced in the routing-badge tooltip.
    * ``matched_rule_id`` — the tag/system rule that fired (or
      ``None`` if no rule matched and the default applied).
    * ``evaluated_rules`` — ordered ids of every rule the evaluator
      tested; used by ``Inspector Routing`` per spec §6.
    * ``quota_state_at_decision`` — snapshot of overall + sonnet
      quota at the moment of evaluation; spec §App A keys
      ``overall_used_pct`` / ``sonnet_used_pct``.
    """

    executor_model: str
    advisor_model: str | None
    advisor_max_uses: int
    effort_level: str
    source: str
    reason: str
    matched_rule_id: int | None
    evaluated_rules: list[int] = field(default_factory=list)
    quota_state_at_decision: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.executor_model:
            raise ValueError("RoutingDecision.executor_model must be non-empty")
        if not _is_known_model(self.executor_model):
            raise ValueError(
                f"RoutingDecision.executor_model {self.executor_model!r} "
                f"is neither a known short name {sorted(KNOWN_EXECUTOR_MODELS)} "
                f"nor a full SDK ID prefixed with "
                f"{EXECUTOR_MODEL_FULL_ID_PREFIX!r}"
            )
        if self.advisor_model is not None and not _is_known_model(self.advisor_model):
            raise ValueError(
                f"RoutingDecision.advisor_model {self.advisor_model!r} is not a "
                f"known short name and does not begin with "
                f"{EXECUTOR_MODEL_FULL_ID_PREFIX!r}"
            )
        if self.effort_level not in KNOWN_EFFORT_LEVELS:
            raise ValueError(
                f"RoutingDecision.effort_level {self.effort_level!r} is not in "
                f"{sorted(KNOWN_EFFORT_LEVELS)}"
            )
        if self.advisor_max_uses < 0:
            raise ValueError(
                f"RoutingDecision.advisor_max_uses must be ≥ 0 (got {self.advisor_max_uses})"
            )
        if self.source not in KNOWN_ROUTING_SOURCES:
            raise ValueError(
                f"RoutingDecision.source {self.source!r} is not in {sorted(KNOWN_ROUTING_SOURCES)}"
            )


def _is_known_model(name: str) -> bool:
    """Return ``True`` if ``name`` is a known short name or full SDK ID."""
    return name in KNOWN_EXECUTOR_MODELS or name.startswith(EXECUTOR_MODEL_FULL_ID_PREFIX)


__all__ = ["RoutingDecision"]
