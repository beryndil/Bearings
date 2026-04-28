"""Numeric and string defaults for the Bearings v1 rebuild.

Source-of-truth notes
---------------------

Every constant in this module is mandated by either:

* ``docs/model-routing-v1-spec.md`` — routing/quota/usage defaults
  (cited per-line by section §);
* ``docs/architecture-v1.md`` — internal-runtime defaults whose
  rationale is documented in §1.1.2 / §5 of the arch doc; or
* ``docs/behavior/<subsystem>.md`` — user-observable timing /
  threshold values whose authoritative source is the per-subsystem
  behavior spec; or
* the project ``CLAUDE.md`` repo invariants (port 8788 + DB at
  ``~/.local/share/bearings-v1/``) that let v0.17.x and v1 run
  side-by-side during the dogfood phase.

Downstream modules MUST import from here instead of hard-coding
literals — the auditor's "no inline literals" gate (item 0.5
done-when) scans every diff under ``src/bearings/`` for numeric /
string defaults that should have come from this module.

Spec §3's priority-ladder values (10/20/30/40/50/60/1000) are
deliberately *not* exposed here. Per ``docs/architecture-v1.md`` §6.5
#7 the source-of-truth for those values is the DB seed in
``db/connection.py`` (the user can edit them after first-run, so a
``Final[int]`` constant would lie). The constants module names the
runtime-tunable defaults; the seed names the (editable) priority
ladder.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Process-level defaults (project CLAUDE.md "Repo invariants")
# ---------------------------------------------------------------------------

# Concurrent-run port: v0.17.x stays on 8787; v1 lives on 8788 so both UIs
# can be hosted at once during dogfood.
DEFAULT_PORT: Final[int] = 8788

# Loopback bind: Bearings is single-user localhost; binding to anything else
# would expose subscription-auth to the LAN.
DEFAULT_HOST: Final[str] = "127.0.0.1"

# DB path: ``~/.local/share/bearings-v1/sessions.db`` per CLAUDE.md "Repo
# invariants". ``expanduser()`` resolves the leading ``~`` at import time so
# downstream code never has to think about it.
DEFAULT_DB_PATH: Final[Path] = Path("~/.local/share/bearings-v1/sessions.db").expanduser()

# ---------------------------------------------------------------------------
# Routing / quota / usage defaults (docs/model-routing-v1-spec.md)
# ---------------------------------------------------------------------------

# Routing preview debounce after the user types in the new-session dialog
# (spec §6 "Reactive behavior" — debounced ~300 ms). The ``_MS`` companion
# is exposed so ``Settings.routing_preview_debounce_ms`` reads naturally as
# an ``int`` field; the ``timedelta`` form is the canonical value.
ROUTING_PREVIEW_DEBOUNCE: Final[timedelta] = timedelta(milliseconds=300)
ROUTING_PREVIEW_DEBOUNCE_MS: Final[int] = 300

# Quota poller cadence (spec §4 — "polls /usage every 5 minutes"). The
# seconds form is exposed for ``Settings.quota_poll_interval_s``.
USAGE_POLL_INTERVAL: Final[timedelta] = timedelta(minutes=5)
USAGE_POLL_INTERVAL_S: Final[int] = 300

# Quota guard downgrade threshold (spec §4 — "if overall_used_pct >= 0.80
# ... downgrade executor; if sonnet_used_pct >= 0.80 and executor ==
# 'sonnet' ... downgrade to haiku"). Spec §13 risk #2 admits this is a
# guess and may become user-tunable; ``Settings.quota_threshold_pct``
# already exposes the override.
QUOTA_THRESHOLD_PCT: Final[float] = 0.80

# Header quota-bar colour transitions (spec §4 + §10 "Quota bars in the
# session header" — "yellow at 80% used, red at 95%").
QUOTA_BAR_YELLOW_PCT: Final[float] = 0.80
QUOTA_BAR_RED_PCT: Final[float] = 0.95

# Override-rate "Review:" highlighting threshold (spec §8 — "Rules with
# override_rate > 0.30 over the last 14 days are surfaced ... as 'Review:'
# highlighted rows").
OVERRIDE_RATE_REVIEW_THRESHOLD: Final[float] = 0.30

# Override-rate rolling window (spec §8 + §10 "Rules to review list" —
# "rules with override rate > 30% in the last 14 days").
OVERRIDE_RATE_WINDOW: Final[timedelta] = timedelta(days=14)
OVERRIDE_RATE_WINDOW_DAYS: Final[int] = 14

# Inspector Usage headroom-chart window (spec §7 "Quota efficiency" + §10
# "Headroom remaining chart" — "rolling 7-day plot").
USAGE_HEADROOM_WINDOW: Final[timedelta] = timedelta(days=7)
USAGE_HEADROOM_WINDOW_DAYS: Final[int] = 7

# Default advisor max-uses per executor pairing (spec §2 default-policy
# table). Sonnet-paired executor gets 5; Haiku-paired gets 3 (the table
# notes Haiku consults less frequently because more turns are mechanical).
DEFAULT_ADVISOR_MAX_USES_SONNET: Final[int] = 5
DEFAULT_ADVISOR_MAX_USES_HAIKU: Final[int] = 3

# Advisor beta-header ID (spec §2 — "behind beta header
# advisor-tool-2026-03-01"). Pinned here so a future GA-without-header
# bump touches a single symbol per arch §5 #1/#2.
ADVISOR_TOOL_BETA_HEADER: Final[str] = "advisor-tool-2026-03-01"

# Spec-vocabulary effort label → SDK ``effort`` literal mapping (arch §5
# #4). The spec writes rules in ``auto``/``low``/``medium``/``high``/
# ``xhigh``; the SDK exposes ``effort`` as a literal taking
# ``low``/``medium``/``high``/``max``. Putting the table here means a
# future SDK literal addition (e.g. ``auto`` becomes a real value) is a
# one-line edit. ``None`` means "omit the field — let the SDK pick".
EFFORT_LEVEL_TO_SDK: Final[dict[str, str | None]] = {
    "auto": None,
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "max",
}

# Executor → SDK ``fallback_model`` mapping (arch §5 #5 — "sonnet → haiku,
# opus → sonnet, haiku → haiku (no further)"). The mapping is total so
# ``EXECUTOR_FALLBACK_MODEL[executor]`` never raises ``KeyError`` for a
# valid executor name.
EXECUTOR_FALLBACK_MODEL: Final[dict[str, str]] = {
    "sonnet": "haiku",
    "opus": "sonnet",
    "haiku": "haiku",
}

# ---------------------------------------------------------------------------
# Internal-runtime defaults (docs/architecture-v1.md §1.1.2)
# ---------------------------------------------------------------------------

# Per-runner WS event ring buffer cap (arch §1.1.2 — "RING_BUFFER_MAX =
# 5000"). Bounds replay buffer growth on long-lived sessions.
RING_BUFFER_MAX: Final[int] = 5000

# Tool-call keepalive tick cadence (arch §1.1.2 — "TOOL_PROGRESS_INTERVAL_S
# = 2.0"). Per-tool-call ProgressTickerManager emits a heartbeat at this
# interval so the UI's elapsed-time readout never freezes.
TOOL_PROGRESS_INTERVAL: Final[timedelta] = timedelta(seconds=2)
TOOL_PROGRESS_INTERVAL_S: Final[float] = 2.0

# WS idle ping interval (arch §1.1.2 — "WS_IDLE_PING_INTERVAL_S = 15.0").
# Keeps long-idle WebSocket connections from being reaped by intermediate
# proxies / NATs.
WS_IDLE_PING_INTERVAL: Final[timedelta] = timedelta(seconds=15)
WS_IDLE_PING_INTERVAL_S: Final[float] = 15.0

# History prefix prime cap (arch §1.1.2 — "HISTORY_PRIME_MAX_CHARS =
# 60_000"). On runner reattach, replay no more than this many chars of
# prior conversation into the prompt prefix.
HISTORY_PRIME_MAX_CHARS: Final[int] = 60_000

# Context-pressure layer inject threshold % (arch §1.1.2 —
# "PRESSURE_INJECT_THRESHOLD_PCT = 70.0"). Above this, ``agent/prompt.py``
# inserts the ``<context-pressure>`` block so the model knows it is near
# the cap. Distinct from the auto-driver's pressure-watchdog handoff
# threshold below — that is a *halt* trigger, this is a *steering* one.
PRESSURE_INJECT_THRESHOLD_PCT: Final[float] = 70.0

# Default per-tool-call output cap (arch §1.1.2 + §4.8 SessionConfig
# default — "tool_output_cap_chars: int = 8000"). Soft cap for streaming;
# hard cap behaviour lives in tool-output-streaming behavior doc.
DEFAULT_TOOL_OUTPUT_CAP_CHARS: Final[int] = 8000

# ---------------------------------------------------------------------------
# Structural validation bounds (well-known facts; not spec-derived)
# ---------------------------------------------------------------------------

# TCP port valid-range floor / ceiling. Used by Settings.port's pydantic
# ``ge=`` / ``le=`` validators so the bounds aren't bare literals at the
# call site (per item 0.5's "no inline literals" gate).
TCP_PORT_MIN: Final[int] = 1
TCP_PORT_MAX: Final[int] = 65_535

# Percentage-as-fraction floor / ceiling (0.0 = 0 %, 1.0 = 100 %).
# Used by every ``*_pct`` Settings field so quota / override-rate
# fractions can't drift outside [0, 1].
PCT_MIN: Final[float] = 0.0
PCT_MAX: Final[float] = 1.0

# ---------------------------------------------------------------------------
# Behavioral defaults (docs/behavior/<subsystem>.md)
# ---------------------------------------------------------------------------

# Auto-driver pressure-watchdog handoff trigger (behavior/checklists.md
# §"Pressure-watchdog handoff request" — "60 % by default"). When the
# leg's reported context pressure crosses this threshold and the agent
# has not emitted a handoff sentinel, the driver injects one nudge before
# treating the quiet turn as a silent-exit failure.
CHECKLIST_DRIVER_PRESSURE_HANDOFF_THRESHOLD_PCT: Final[float] = 60.0

# Auto-driver per-item leg cap (behavior/checklists.md §"Sentinel safety
# caps" — "default 5"). After this many legs on a single item, the driver
# halts that item with ``failure_reason = max_legs_per_item exceeded``.
CHECKLIST_DRIVER_MAX_LEGS_PER_ITEM: Final[int] = 5

# Auto-driver per-run item cap (behavior/checklists.md — "default 50").
# After touching this many items in a single run, the driver halts with
# ``Halted: max items``.
CHECKLIST_DRIVER_MAX_ITEMS_PER_RUN: Final[int] = 50

# Auto-driver blocking-followup nesting cap (behavior/checklists.md —
# "default 3"). Beyond this, the followup is treated as a malformed
# sentinel and ignored.
CHECKLIST_DRIVER_MAX_FOLLOWUP_DEPTH: Final[int] = 3

# ``bearings todo recent`` default lookback (behavior/bearings-cli.md
# §"bearings todo recent" — "Lists entries that changed in the last N
# days (default 7)").
BEARINGS_TODO_RECENT_DEFAULT_DAYS: Final[int] = 7


__all__ = [
    "ADVISOR_TOOL_BETA_HEADER",
    "BEARINGS_TODO_RECENT_DEFAULT_DAYS",
    "CHECKLIST_DRIVER_MAX_FOLLOWUP_DEPTH",
    "CHECKLIST_DRIVER_MAX_ITEMS_PER_RUN",
    "CHECKLIST_DRIVER_MAX_LEGS_PER_ITEM",
    "CHECKLIST_DRIVER_PRESSURE_HANDOFF_THRESHOLD_PCT",
    "DEFAULT_ADVISOR_MAX_USES_HAIKU",
    "DEFAULT_ADVISOR_MAX_USES_SONNET",
    "DEFAULT_DB_PATH",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_TOOL_OUTPUT_CAP_CHARS",
    "EFFORT_LEVEL_TO_SDK",
    "EXECUTOR_FALLBACK_MODEL",
    "HISTORY_PRIME_MAX_CHARS",
    "OVERRIDE_RATE_REVIEW_THRESHOLD",
    "OVERRIDE_RATE_WINDOW",
    "OVERRIDE_RATE_WINDOW_DAYS",
    "PCT_MAX",
    "PCT_MIN",
    "PRESSURE_INJECT_THRESHOLD_PCT",
    "QUOTA_BAR_RED_PCT",
    "QUOTA_BAR_YELLOW_PCT",
    "QUOTA_THRESHOLD_PCT",
    "RING_BUFFER_MAX",
    "ROUTING_PREVIEW_DEBOUNCE",
    "ROUTING_PREVIEW_DEBOUNCE_MS",
    "TCP_PORT_MAX",
    "TCP_PORT_MIN",
    "TOOL_PROGRESS_INTERVAL",
    "TOOL_PROGRESS_INTERVAL_S",
    "USAGE_HEADROOM_WINDOW",
    "USAGE_HEADROOM_WINDOW_DAYS",
    "USAGE_POLL_INTERVAL",
    "USAGE_POLL_INTERVAL_S",
    "WS_IDLE_PING_INTERVAL",
    "WS_IDLE_PING_INTERVAL_S",
]
