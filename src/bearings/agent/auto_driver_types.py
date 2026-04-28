"""Frozen dataclasses + the ``DriverRuntime`` Protocol for the auto-driver.

Per ``docs/architecture-v1.md`` §1.1.4 + §4.6: this module owns the
type surface that ``agent/auto_driver.py`` (the canonical ``Driver``
class) and ``agent/auto_driver_runtime.py`` (the FastAPI-aware concrete
binding) share. Splitting the types out is the v1 cycle-break: the
``Driver`` does not import ``web``; the runtime impl in
``auto_driver_runtime.py`` takes a :class:`bearings.agent.runner.RunnerFactory`
Protocol injected at construction.

Public surface:

* :class:`DriverConfig` — per-run knobs the user sets on Start
  (failure_policy, visit_existing) plus the safety caps from
  :mod:`bearings.config.constants`.
* :class:`DriverOutcome` — string-enum-ish; the user-visible terminal
  outcome strings.
* :class:`DriverResult` — what :meth:`Driver.drive` returns once the
  outer loop concludes.
* :class:`DriverRuntime` — Protocol the ``Driver`` calls to spawn legs,
  run turns, tear down legs, query context-pressure. The concrete
  binding lives in ``auto_driver_runtime.py`` and is FastAPI-aware;
  tests inject a stub.
"""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Protocol

from bearings.config.constants import (
    AUTO_DRIVER_FAILURE_POLICY_HALT,
    CHECKLIST_DRIVER_MAX_FOLLOWUP_DEPTH,
    CHECKLIST_DRIVER_MAX_ITEMS_PER_RUN,
    CHECKLIST_DRIVER_MAX_LEGS_PER_ITEM,
    CHECKLIST_DRIVER_MAX_TURNS_PER_LEG,
    CHECKLIST_DRIVER_PRESSURE_HANDOFF_THRESHOLD_PCT,
    DRIVER_OUTCOME_COMPLETED,
    DRIVER_OUTCOME_HALTED_EMPTY,
    DRIVER_OUTCOME_HALTED_FAILURE_TEMPLATE,
    DRIVER_OUTCOME_HALTED_MAX_ITEMS,
    DRIVER_OUTCOME_HALTED_STOPPED,
    KNOWN_AUTO_DRIVER_FAILURE_POLICIES,
)


@dataclass(frozen=True)
class DriverConfig:
    """Per-Start configuration for one autonomous driver run.

    Defaults match behavior/checklists.md §"Run-control surface" /
    §"Sentinel safety caps the user observes":

    * ``failure_policy`` defaults to ``halt`` (the spec calls it the
      default).
    * ``visit_existing`` defaults to ``False`` (Start spawns fresh
      legs unless the toggle is explicitly enabled).
    * ``max_legs_per_item`` / ``max_items_per_run`` /
      ``max_followup_depth`` / ``max_turns_per_leg`` /
      ``pressure_handoff_threshold_pct`` come from
      :mod:`bearings.config.constants` so the audit can grep for
      inline literals at the call site.
    """

    failure_policy: str = AUTO_DRIVER_FAILURE_POLICY_HALT
    visit_existing: bool = False
    max_legs_per_item: int = CHECKLIST_DRIVER_MAX_LEGS_PER_ITEM
    max_items_per_run: int = CHECKLIST_DRIVER_MAX_ITEMS_PER_RUN
    max_followup_depth: int = CHECKLIST_DRIVER_MAX_FOLLOWUP_DEPTH
    max_turns_per_leg: int = CHECKLIST_DRIVER_MAX_TURNS_PER_LEG
    pressure_handoff_threshold_pct: float = CHECKLIST_DRIVER_PRESSURE_HANDOFF_THRESHOLD_PCT

    def __post_init__(self) -> None:
        if self.failure_policy not in KNOWN_AUTO_DRIVER_FAILURE_POLICIES:
            raise ValueError(
                f"DriverConfig.failure_policy {self.failure_policy!r} not in "
                f"{sorted(KNOWN_AUTO_DRIVER_FAILURE_POLICIES)}"
            )
        for name, value in (
            ("max_legs_per_item", self.max_legs_per_item),
            ("max_items_per_run", self.max_items_per_run),
            ("max_followup_depth", self.max_followup_depth),
            ("max_turns_per_leg", self.max_turns_per_leg),
        ):
            if value <= 0:
                raise ValueError(f"DriverConfig.{name} must be > 0 (got {value})")
        if not 0.0 < self.pressure_handoff_threshold_pct <= 100.0:
            raise ValueError(
                f"DriverConfig.pressure_handoff_threshold_pct must be in (0, 100] "
                f"(got {self.pressure_handoff_threshold_pct})"
            )


@dataclass(frozen=True)
class DriverOutcome:
    """Wrapper for the user-observable outcome strings.

    Class-level attributes pin the canonical strings from
    :mod:`bearings.config.constants` so the call-site reads
    :attr:`DriverOutcome.COMPLETED` instead of the bare constant —
    matches the v0.17.x convention referenced by behavior docs.
    """

    COMPLETED: str = DRIVER_OUTCOME_COMPLETED
    HALTED_EMPTY: str = DRIVER_OUTCOME_HALTED_EMPTY
    HALTED_MAX_ITEMS: str = DRIVER_OUTCOME_HALTED_MAX_ITEMS
    HALTED_STOPPED: str = DRIVER_OUTCOME_HALTED_STOPPED

    @staticmethod
    def halted_failure(item_id: int) -> str:
        """Format the per-item failure string with ``item_id`` substituted."""
        return DRIVER_OUTCOME_HALTED_FAILURE_TEMPLATE.format(n=item_id)


@dataclass(frozen=True)
class DriverResult:
    """Terminal result returned by :meth:`Driver.drive`.

    ``outcome`` is one of the user-visible strings (see
    :class:`DriverOutcome`); ``items_completed`` /
    ``items_failed`` / ``items_blocked`` / ``items_skipped`` /
    ``legs_spawned`` / ``items_attempted`` mirror the run row counters
    so the caller (typically a route handler) can persist + return one
    payload without re-querying the DB.
    """

    outcome: str
    outcome_reason: str | None
    items_completed: int
    items_failed: int
    items_blocked: int
    items_skipped: int
    items_attempted: int
    legs_spawned: int
    legs: list[str] = field(default_factory=list)


class DriverRuntime(Protocol):
    """Per arch §4.6 — the surface ``Driver`` calls into.

    Two boundary methods (spawn / teardown) plus the per-turn driver
    (``run_turn``) plus a pressure-readout (``last_context_percentage``).
    The concrete binding lives in ``agent/auto_driver_runtime.py``;
    tests inject a stub that fakes the SDK lifecycle.

    All methods are async because the production binding awaits the
    runner factory (which awaits an SDK subprocess spawn) and the
    per-turn run awaits ``runner.emit`` events.
    """

    async def spawn_leg(
        self,
        *,
        item_id: int,
        leg_number: int,
        plug: str | None,
    ) -> str:
        """Spawn (or visit) the chat session for ``(item_id, leg_number)``.

        Returns the chat session id. ``plug`` is the handoff plug body
        from a predecessor leg's ``handoff`` sentinel; ``None`` for the
        first leg of an item.
        """

    async def run_turn(
        self,
        *,
        leg_session_id: str,
        prompt: str,
    ) -> str:
        """Run one turn on ``leg_session_id`` and return the assistant body.

        The body is the content the sentinel parser scans. The driver
        loops over this method until a terminal sentinel surfaces or
        ``max_turns_per_leg`` is hit.
        """

    async def teardown_leg(self, *, leg_session_id: str) -> None:
        """Drain runner / persist state / close the leg.

        Called when the driver finishes with a leg (sentinel-emitted
        completion, handoff cutover, leg-cap halt, item-blocked stop).
        Must be idempotent — a re-call on an already-torn-down leg is
        a no-op.
        """

    def last_context_percentage(self, leg_session_id: str) -> float | None:
        """Most recent context-window percentage for ``leg_session_id``.

        ``None`` when the SDK has not yet reported a usage value (e.g.
        the leg has not finished its first turn). Drives the
        pressure-watchdog handoff request per behavior/checklists.md
        §"Pressure-watchdog handoff request".
        """


class StopRequested(Exception):
    """Raised inside the driver loop when the user pressed Stop.

    A control-flow exception (not an error). Caught at the
    :meth:`Driver.drive` outer-loop boundary which transitions the run
    to ``finished`` with outcome :attr:`DriverOutcome.HALTED_STOPPED`.
    """


# Type alias for the readonly factory-style closure the driver uses to
# resolve a runner from a leg's session id without importing the
# concrete registry. Useful to expose a tiny surface to test stubs.
type RunnerLookup = Awaitable[object]


__all__ = [
    "DriverConfig",
    "DriverOutcome",
    "DriverResult",
    "DriverRuntime",
    "RunnerLookup",
    "StopRequested",
]
