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
# Streaming-protocol defaults (item 1.2; docs/behavior/tool-output-streaming.md)
# ---------------------------------------------------------------------------

# Per-event ``ToolOutputDelta.delta`` cap for the wire protocol. The behavior
# doc (``docs/behavior/tool-output-streaming.md`` §"Very-long-output
# truncation rules") prescribes user-visible soft/hard caps for display
# and persistence; this constant is the *transport*-level cap that keeps
# any single WebSocket frame from exceeding a tractable size. Backend
# splits oversized deltas into multiple :class:`ToolOutputDelta` events
# preserving total payload (codepoint-safe — Python ``str`` slicing splits
# at codepoints). 64 KiB chosen so a typical 100k tool-output payload
# becomes ≤2 frames; larger values risk client-side rendering hitches.
STREAM_MAX_DELTA_CHARS: Final[int] = 64_000

# Hard cap on total per-tool-call output bytes streamed through the
# protocol. Beyond this cap the runner emits a :class:`ToolOutputDelta`
# carrying the truncation marker (``[truncated — N chars elided]``) and
# drops further deltas for that ``tool_call_id``. Per behavior doc
# §"Very-long-output truncation rules" — "the marker always appears at
# the end of the persisted body". 1 MiB chosen as a generous ceiling
# that comfortably accommodates `cargo build` / `pytest -v` style
# outputs while keeping any single tool's runaway loop from saturating
# the per-runner ring buffer.
STREAM_MAX_TOOL_OUTPUT_CHARS: Final[int] = 1_048_576

# Truncation marker template. ``{n}`` is the chars-elided count; the
# template includes the surrounding brackets to keep the contract
# inline-literal-free at the call site. Behavior-doc-mandated wording.
STREAM_TRUNCATION_MARKER_TEMPLATE: Final[str] = "\n[truncated — {n} chars elided]"

# Heartbeat ping interval for idle WebSocket connections. Aliases
# :data:`WS_IDLE_PING_INTERVAL_S` so the streaming layer's import surface
# names the concern at the call site without forcing every consumer to
# know which subsystem owns the underlying interval. The two MUST stay
# numerically equal (asserted at module import below).
STREAM_HEARTBEAT_INTERVAL_S: Final[float] = WS_IDLE_PING_INTERVAL_S

# ---------------------------------------------------------------------------
# Session module vocabulary (arch §4.1, §4.8; SDK shapes verified via
# context7 ``/anthropics/claude-agent-sdk-python`` queried 2026-04-28)
# ---------------------------------------------------------------------------

# Canonical short-name executor models the routing layer accepts as
# ``RoutingDecision.executor_model`` (spec §App A). Long-form SDK model
# IDs (e.g. ``claude-sonnet-4-5``) are accepted via the
# ``EXECUTOR_MODEL_FULL_ID_PREFIX`` test below; the two together cover
# both the user-facing vocabulary in tag rules and the SDK pinning the
# rebuild does in ``agent/options.py:build_options`` (item 1.2). The
# ``opusplan`` short name is the spec §1 alias the resolution stage
# applies when ``executor=opus`` and the user has not explicitly typed
# ``opus`` (per spec §1 "executor=opus → resolve to opusplan unless
# explicitly typed 'opus'").
KNOWN_EXECUTOR_MODELS: Final[frozenset[str]] = frozenset({"sonnet", "haiku", "opus", "opusplan"})

# A ``RoutingDecision.executor_model`` whose value starts with this
# prefix is accepted as a full SDK model ID without further short-name
# enumeration; the SDK resolves it. This is the boundary-validator side
# of arch §5 #4 "future SDK literal addition is a one-line table edit".
EXECUTOR_MODEL_FULL_ID_PREFIX: Final[str] = "claude-"

# Effort labels the spec writes routing rules in (spec §App A
# ``effort_level``). The translation to SDK ``effort`` literal lives
# already in ``EFFORT_LEVEL_TO_SDK`` above; this set is the validator
# input alphabet.
KNOWN_EFFORT_LEVELS: Final[frozenset[str]] = frozenset({"auto", "low", "medium", "high", "xhigh"})

# ``RoutingDecision.source`` valid values (spec §App A enum). The seven
# values cover every shape ``agent/routing.py:evaluate`` (item 1.8) and
# ``agent/quota.py:apply_quota_guard`` (item 1.8) can produce, plus the
# ``unknown_legacy`` carrier per spec §5 "Backfill for legacy data".
KNOWN_ROUTING_SOURCES: Final[frozenset[str]] = frozenset(
    {
        "tag_rule",
        "system_rule",
        "default",
        "manual",
        "quota_downgrade",
        "manual_override_quota",
        "unknown_legacy",
    }
)

# SDK ``permission_mode`` literal alphabet, per
# ``claude_agent_sdk.ClaudeAgentOptions`` (context7 query
# ``/anthropics/claude-agent-sdk-python`` 2026-04-28). Note both
# ``dontAsk`` and ``auto`` are valid current literals; v0.17.x predates
# both. ``AgentSession.set_permission_mode`` (arch §2.1 + §5 #9)
# validates against this set before forwarding to the live client.
KNOWN_SDK_PERMISSION_MODES: Final[frozenset[str]] = frozenset(
    {"default", "acceptEdits", "plan", "bypassPermissions", "dontAsk", "auto"}
)

# SDK ``setting_sources`` literal alphabet (context7 query as above —
# the SDK accepts ``"user"``, ``"project"``, ``"local"``).
# ``SessionConfig`` validates each entry of its ``setting_sources``
# tuple against this set.
KNOWN_SDK_SETTING_SOURCES: Final[frozenset[str]] = frozenset({"user", "project", "local"})

# Permission-profile presets — Bearings' own abstraction layered on top
# of SDK ``permission_mode`` + ``allowed_tools`` + ``disallowed_tools``.
# The three presets cover the three mid-level postures: read-only
# inspection (RESTRICTED), normal day-to-day editing (STANDARD), and
# fully autonomous (EXPANDED). Profile names are user-facing strings;
# the ``PermissionProfile`` enum in ``agent/session.py`` mirrors them.
PERMISSION_PROFILE_NAMES: Final[frozenset[str]] = frozenset({"restricted", "standard", "expanded"})

# Profile → SDK ``permission_mode`` resolution table. The table values
# are validated against ``KNOWN_SDK_PERMISSION_MODES`` by an init-time
# self-check in ``agent/session.py``.
PERMISSION_PROFILE_TO_SDK_MODE: Final[dict[str, str]] = {
    "restricted": "default",
    "standard": "acceptEdits",
    "expanded": "bypassPermissions",
}

# Profile → SDK ``allowed_tools`` allowance. ``RESTRICTED`` allows
# read-only inspection tools only; ``STANDARD`` adds the everyday
# write/edit/bash set; ``EXPANDED`` is empty because under
# ``bypassPermissions`` the allowlist is moot — every tool is
# auto-approved at the SDK boundary. Tuples are immutable; the resolver
# in ``agent/session.py`` casts to ``list`` only at the SDK boundary.
PERMISSION_PROFILE_ALLOWED_TOOLS: Final[dict[str, tuple[str, ...]]] = {
    "restricted": ("Read", "Glob", "Grep", "WebFetch", "WebSearch"),
    "standard": (
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        "Bash",
        "WebFetch",
        "WebSearch",
        "Task",
    ),
    "expanded": (),
}

# Profile → SDK ``disallowed_tools`` deny list. Only ``RESTRICTED``
# carries explicit denies; the other two profiles delegate to the
# permission_mode (acceptEdits / bypassPermissions).
PERMISSION_PROFILE_DISALLOWED_TOOLS: Final[dict[str, tuple[str, ...]]] = {
    "restricted": ("Bash", "Write", "Edit"),
    "standard": (),
    "expanded": (),
}

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

# ---------------------------------------------------------------------------
# Checkpoints + templates (item 1.3; arch §1.1.3 db/checkpoints.py +
# db/templates.py; arch §5 #12 — Bearings owns its named-snapshot
# checkpoints rather than the SDK ``enable_file_checkpointing``
# automatic-write-snapshot primitive; behavior surfaces in
# ``docs/behavior/chat.md`` §"Slash commands in the composer" /``
# docs/behavior/context-menus.md`` §"Checkpoint (gutter chip)" / §"Session
# row" ``session.save_as_template``).
# ---------------------------------------------------------------------------

# Per-session ceiling on stored checkpoints. The behavior docs do not
# mandate a retention policy; this constant is the runtime-tunable
# default the API layer (item 1.10) enforces when ``checkpoints.create``
# would push a session past the cap. Chosen high enough that a
# disciplined user almost never bumps into it (typical session has 1-5
# checkpoints) yet low enough that a runaway client cannot bloat the DB.
MAX_CHECKPOINTS_PER_SESSION: Final[int] = 50

# Default label applied when the user invokes the ``/checkpoint`` slash
# command without an explicit label. The ``{n}`` placeholder is the
# 1-indexed ordinal of the checkpoint within the session (filled by the
# DB helper at create time); per ``docs/behavior/chat.md`` §"Slash
# commands" the label is what surfaces in the gutter chip the user
# right-clicks on per ``docs/behavior/context-menus.md`` §"Checkpoint".
DEFAULT_CHECKPOINT_LABEL_TEMPLATE: Final[str] = "Checkpoint {n}"

# Maximum length the API layer accepts on a checkpoint label / template
# name / template description. Caps protect the WS frame and the gutter
# chip's render width without quoting a UI-pixel number; chosen to be
# generous (a typical label is ≤40 chars) but bounded.
CHECKPOINT_LABEL_MAX_LENGTH: Final[int] = 200
TEMPLATE_NAME_MAX_LENGTH: Final[int] = 200
TEMPLATE_DESCRIPTION_MAX_LENGTH: Final[int] = 1000

# Default template field values when a user creates a template via the
# ``session.save_as_template`` context-menu action without overriding
# the routing/permission fields. Mirror the spec §3 default routing
# rule (priority 1000, ``always`` match, sonnet+opus advisor, auto
# effort) and the standard permission profile, so a "save current as
# template" with no edits produces a workhorse-default preset.
DEFAULT_TEMPLATE_MODEL: Final[str] = "sonnet"
DEFAULT_TEMPLATE_ADVISOR_MODEL: Final[str | None] = "opus"
DEFAULT_TEMPLATE_ADVISOR_MAX_USES: Final[int] = 5
DEFAULT_TEMPLATE_EFFORT_LEVEL: Final[str] = "auto"
DEFAULT_TEMPLATE_PERMISSION_PROFILE: Final[str] = "standard"

# ---------------------------------------------------------------------------
# Tags + tag memories (item 1.4; arch §1.1.3 ``db/tags.py`` +
# ``db/memories.py``; arch §1.1.5 ``web/routes/tags.py`` +
# ``web/routes/memories.py``; behavior surfaces in ``docs/behavior/chat.md``
# §"When the user creates a chat", ``docs/behavior/checklists.md``
# §"…inherits the checklist's working directory, model, and tags",
# ``docs/behavior/context-menus.md`` §"Tag (sidebar tag chip in the filter
# panel)" + §"Tag chip (attached to a session, …)"). Spec §App A pins the
# allowed alphabet for ``tags.default_model`` (mirrors templates' validator
# in ``db/templates.py``).
# ---------------------------------------------------------------------------

# Tag-name maximum length. Tag names surface as sidebar filter chips and
# inside the new-session-dialog tag picker (per ``docs/behavior/chat.md``
# §"When the user creates a chat"); the cap is generous enough for the
# slash-namespaced names the rebuild's test fixtures use
# (``bearings/architect`` ≈ 18 chars) and for arbitrary user labels,
# while bounded so the tag-picker dropdown doesn't try to render a
# pathological name. Mirrors :data:`TEMPLATE_NAME_MAX_LENGTH` for
# consistency across user-facing label fields.
TAG_NAME_MAX_LENGTH: Final[int] = 200

# Tag-color maximum length. Colors are user-supplied free-text per the
# ``tags.color`` schema column (no CHECK constraint at the schema level
# — the color field is purely cosmetic and validation is the API
# layer's job). Cap chosen long enough for ``rgba(...)`` / ``oklch(...)``
# strings without needing a CSS parser at the wire boundary; short
# enough that an absurd value can't bloat the row.
TAG_COLOR_MAX_LENGTH: Final[int] = 64

# Tag-group separator. The schema does not declare a separate
# ``tag_groups`` table; tag groups are expressed by slash-namespacing
# the tag name (``<group>/<name>``). The separator is a single character
# so the group prefix is unambiguous and a bare name (no separator) is
# treated as the unnamed/default group. Decided-and-documented per the
# item-1.4 done-when's "tag groups" requirement: the schema landed in
# 0.4 with no group column, so the rebuild adopts the slash-namespace
# convention already in test fixtures (``bearings/architect``,
# ``bearings/exec``).
TAG_GROUP_SEPARATOR: Final[str] = "/"

# Tag-memory title maximum length. Titles surface in the memories editor
# UI (per ``docs/behavior/vault.md`` cross-reference) as a one-line
# summary above the body editor; same cap as tag names so the two label
# surfaces share a single character budget.
TAG_MEMORY_TITLE_MAX_LENGTH: Final[int] = 200

# Tag-memory body maximum length. Memories are system-prompt fragments
# (per arch §1.1.3 — "tag memories as system-prompt fragments that the
# prompt assembler reads per turn"); the cap bounds any single fragment
# so a runaway memory cannot saturate the prompt-prime budget
# :data:`HISTORY_PRIME_MAX_CHARS` upstream. Chosen at half of that
# budget so up to two large memories can coexist.
TAG_MEMORY_BODY_MAX_LENGTH: Final[int] = 30_000


# Self-consistency: every profile that appears in the resolution tables
# below must also appear in :data:`PERMISSION_PROFILE_NAMES`, and every
# resolved SDK mode must be a member of :data:`KNOWN_SDK_PERMISSION_MODES`.
# Asserting at import time means a future hand-edit cannot drift one of
# the four parallel tables silently — an inconsistent mapping fails
# ``import bearings.config.constants`` itself, which the linter and the
# test runner both pick up before any downstream logic executes.
assert set(PERMISSION_PROFILE_TO_SDK_MODE) == PERMISSION_PROFILE_NAMES
assert set(PERMISSION_PROFILE_ALLOWED_TOOLS) == PERMISSION_PROFILE_NAMES
assert set(PERMISSION_PROFILE_DISALLOWED_TOOLS) == PERMISSION_PROFILE_NAMES
assert set(PERMISSION_PROFILE_TO_SDK_MODE.values()) <= KNOWN_SDK_PERMISSION_MODES
assert STREAM_HEARTBEAT_INTERVAL_S == WS_IDLE_PING_INTERVAL_S


__all__ = [
    "ADVISOR_TOOL_BETA_HEADER",
    "BEARINGS_TODO_RECENT_DEFAULT_DAYS",
    "CHECKLIST_DRIVER_MAX_FOLLOWUP_DEPTH",
    "CHECKLIST_DRIVER_MAX_ITEMS_PER_RUN",
    "CHECKLIST_DRIVER_MAX_LEGS_PER_ITEM",
    "CHECKLIST_DRIVER_PRESSURE_HANDOFF_THRESHOLD_PCT",
    "CHECKPOINT_LABEL_MAX_LENGTH",
    "DEFAULT_ADVISOR_MAX_USES_HAIKU",
    "DEFAULT_ADVISOR_MAX_USES_SONNET",
    "DEFAULT_CHECKPOINT_LABEL_TEMPLATE",
    "DEFAULT_DB_PATH",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_TEMPLATE_ADVISOR_MAX_USES",
    "DEFAULT_TEMPLATE_ADVISOR_MODEL",
    "DEFAULT_TEMPLATE_EFFORT_LEVEL",
    "DEFAULT_TEMPLATE_MODEL",
    "DEFAULT_TEMPLATE_PERMISSION_PROFILE",
    "DEFAULT_TOOL_OUTPUT_CAP_CHARS",
    "EFFORT_LEVEL_TO_SDK",
    "EXECUTOR_FALLBACK_MODEL",
    "EXECUTOR_MODEL_FULL_ID_PREFIX",
    "HISTORY_PRIME_MAX_CHARS",
    "KNOWN_EFFORT_LEVELS",
    "KNOWN_EXECUTOR_MODELS",
    "KNOWN_ROUTING_SOURCES",
    "KNOWN_SDK_PERMISSION_MODES",
    "KNOWN_SDK_SETTING_SOURCES",
    "MAX_CHECKPOINTS_PER_SESSION",
    "OVERRIDE_RATE_REVIEW_THRESHOLD",
    "OVERRIDE_RATE_WINDOW",
    "OVERRIDE_RATE_WINDOW_DAYS",
    "PCT_MAX",
    "PCT_MIN",
    "PERMISSION_PROFILE_ALLOWED_TOOLS",
    "PERMISSION_PROFILE_DISALLOWED_TOOLS",
    "PERMISSION_PROFILE_NAMES",
    "PERMISSION_PROFILE_TO_SDK_MODE",
    "PRESSURE_INJECT_THRESHOLD_PCT",
    "QUOTA_BAR_RED_PCT",
    "QUOTA_BAR_YELLOW_PCT",
    "QUOTA_THRESHOLD_PCT",
    "RING_BUFFER_MAX",
    "ROUTING_PREVIEW_DEBOUNCE",
    "ROUTING_PREVIEW_DEBOUNCE_MS",
    "STREAM_HEARTBEAT_INTERVAL_S",
    "STREAM_MAX_DELTA_CHARS",
    "STREAM_MAX_TOOL_OUTPUT_CHARS",
    "STREAM_TRUNCATION_MARKER_TEMPLATE",
    "TAG_COLOR_MAX_LENGTH",
    "TAG_GROUP_SEPARATOR",
    "TAG_MEMORY_BODY_MAX_LENGTH",
    "TAG_MEMORY_TITLE_MAX_LENGTH",
    "TAG_NAME_MAX_LENGTH",
    "TCP_PORT_MAX",
    "TCP_PORT_MIN",
    "TEMPLATE_DESCRIPTION_MAX_LENGTH",
    "TEMPLATE_NAME_MAX_LENGTH",
    "TOOL_PROGRESS_INTERVAL",
    "TOOL_PROGRESS_INTERVAL_S",
    "USAGE_HEADROOM_WINDOW",
    "USAGE_HEADROOM_WINDOW_DAYS",
    "USAGE_POLL_INTERVAL",
    "USAGE_POLL_INTERVAL_S",
    "WS_IDLE_PING_INTERVAL",
    "WS_IDLE_PING_INTERVAL_S",
]
