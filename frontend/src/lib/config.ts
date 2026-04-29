/**
 * Frontend constants — every magic literal the UI references lives
 * here so a coding-standards review can audit "no inline literals" by
 * grepping for the imported names rather than chasing duplication.
 *
 * The names mirror :mod:`bearings.config.constants` on the backend
 * where the meaning is shared (e.g. session-kind alphabet); the values
 * are duplicated rather than synced because the backend module is
 * Python-only. A drift between the two surfaces is a behavioural bug
 * caught by the backend's :data:`KNOWN_SESSION_KINDS` validator the
 * first time a session of an unknown kind reaches the route.
 */

// ---- API endpoints ---------------------------------------------------------

/** Base path for FastAPI routes; vite.config proxies this to port 8788 in dev. */
export const API_BASE = "/api";

/** ``GET /api/sessions`` — sidebar list source per ``docs/behavior/chat.md``. */
export const API_SESSIONS_ENDPOINT = `${API_BASE}/sessions`;

/** ``GET /api/tags`` — tag list source per ``docs/behavior/chat.md`` §"creates a chat". */
export const API_TAGS_ENDPOINT = `${API_BASE}/tags`;

/** ``GET /api/sessions/{id}/tags`` — per-session tag list. */
export const sessionTagsEndpoint = (sessionId: string): string =>
  `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/tags`;

/**
 * ``GET /api/checklists/{id}`` — bundled overview (items + active run)
 * per :func:`bearings.web.routes.checklists.get_overview`. The
 * ChecklistView (item 2.7) reads this on mount + re-reads while a run
 * is live so the status line ticks per ``docs/behavior/checklists.md``
 * §"Run-control surface".
 */
export const apiChecklistEndpoint = (checklistId: string): string =>
  `${API_BASE}/checklists/${encodeURIComponent(checklistId)}`;

/** ``POST /api/checklists/{id}/items`` — create a new item. */
export const apiChecklistItemsEndpoint = (checklistId: string): string =>
  `${apiChecklistEndpoint(checklistId)}/items`;

/**
 * ``…/api/checklist-items/{id}`` — base path for the per-item routes.
 * Subpaths the client appends: ``/check``, ``/uncheck``, ``/block``,
 * ``/unblock``, ``/link``, ``/unlink``, ``/legs``, ``/move``,
 * ``/indent``, ``/outdent``, ``/spawn-chat`` (item 1.7's paired-chat
 * spawn route).
 */
export const apiChecklistItemEndpoint = (itemId: number): string =>
  `${API_BASE}/checklist-items/${itemId}`;

/**
 * ``…/api/checklists/{id}/run`` — base path for run-control routes:
 * ``/start``, ``/stop``, ``/pause``, ``/resume``, ``/skip-current``,
 * ``/status``.
 */
export const apiChecklistRunEndpoint = (checklistId: string): string =>
  `${apiChecklistEndpoint(checklistId)}/run`;

/**
 * ``GET /api/sessions/{id}/messages`` — per-session transcript fetch
 * surface (item 1.9; ``src/bearings/web/routes/messages.py``). The
 * SvelteKit client reads it once on session-select to hydrate the
 * conversation pane with the persisted history; live deltas arrive
 * over the WebSocket below.
 */
export const sessionMessagesEndpoint = (sessionId: string): string =>
  `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/messages`;

/** ``GET /api/messages/{id}`` — single-row fetch (inspector "Why this model?"). */
export const messageEndpoint = (messageId: string): string =>
  `${API_BASE}/messages/${encodeURIComponent(messageId)}`;

/**
 * ``POST /api/routing/preview`` — new-session dialog's reactive
 * routing preview surface (spec §6 + §9). Body shape: ``{ tags:
 * int[], message: str }``; response shape: ``RoutingPreviewOut`` per
 * ``src/bearings/web/models/routing.py`` mirrored on
 * :interface:`RoutingPreview` in ``api/routing.ts``.
 */
export const API_ROUTING_PREVIEW_ENDPOINT = `${API_BASE}/routing/preview`;

/**
 * ``GET /api/quota/current`` — latest snapshot for the in-dialog
 * QuotaBars (spec §8 / §9 + §10 "Quota bars in the session header").
 * Response shape mirrored on :interface:`QuotaSnapshot` in
 * ``api/quota.ts``.
 */
export const API_QUOTA_CURRENT_ENDPOINT = `${API_BASE}/quota/current`;

/**
 * ``GET /api/quota/history?days=7`` — rolling-window quota snapshots
 * for the InspectorUsage "Headroom remaining" chart (spec §7
 * "Quota efficiency" + §10 "Headroom remaining chart"). Response
 * shape: ``QuotaSnapshot[]`` (oldest-first per
 * :func:`bearings.web.routes.quota.get_history`).
 */
export const API_QUOTA_HISTORY_ENDPOINT = `${API_BASE}/quota/history`;

/**
 * ``GET /api/usage/by_model?period=week`` — InspectorUsage by-model
 * table source (spec §7 "Quota efficiency" + §10 "By model table").
 * Response shape: ``UsageByModelRow[]`` per
 * :class:`bearings.web.models.usage.UsageByModelRow`, mirrored on
 * :interface:`UsageByModelRow` in ``api/usage.ts``.
 */
export const API_USAGE_BY_MODEL_ENDPOINT = `${API_BASE}/usage/by_model`;

/**
 * ``GET /api/usage/override_rates?days=14`` — InspectorUsage
 * "Rules to review" source (spec §8 "Override-rate calculation"
 * + §10 "Rules to review list" — rules with override rate > 30 %
 * over the last 14 days). Mirrored on :interface:`OverrideRateOut`
 * in ``api/usage.ts``.
 */
export const API_USAGE_OVERRIDE_RATES_ENDPOINT = `${API_BASE}/usage/override_rates`;

// ---- WebSocket streaming surface ------------------------------------------

/**
 * Per-session WebSocket path the runtime fans out
 * :class:`bearings.agent.events.AgentEvent` frames over (item 1.2;
 * ``src/bearings/web/streaming.py``). Vite's dev proxy forwards
 * ``/ws/*`` to the FastAPI backend on the configured port.
 */
export const sessionStreamPath = (sessionId: string): string =>
  `/ws/sessions/${encodeURIComponent(sessionId)}`;

/**
 * Resume cursor parameter — mirrors :data:`bearings.web.streaming.SINCE_SEQ_QUERY_PARAM`.
 * The reconnect path appends ``?since_seq=<n>`` so the server replays
 * everything past ``n`` from its ring buffer per
 * ``docs/behavior/tool-output-streaming.md`` §"Reconnect / replay".
 */
export const WS_SINCE_SEQ_QUERY_PARAM = "since_seq";

/**
 * Frame ``kind`` values mirror :data:`bearings.web.serialize.FRAME_KIND_*`.
 * The discriminator literal a parsed envelope carries — used by
 * :func:`parseStreamFrame` in ``api/streaming.ts`` to dispatch to the
 * event vs heartbeat branch without re-deciding spelling at the call
 * site.
 */
export const WS_FRAME_KIND_EVENT = "event";
export const WS_FRAME_KIND_HEARTBEAT = "heartbeat";

// ---- Session-kind alphabet (mirrors backend ``KNOWN_SESSION_KINDS``) ------

/** Chat-kind session — composer + transcript per ``docs/behavior/chat.md``. */
export const SESSION_KIND_CHAT = "chat";

/** Checklist-kind session — structured-list pane per ``docs/behavior/checklists.md``. */
export const SESSION_KIND_CHECKLIST = "checklist";

/** The full alphabet; iterated by the kind-indicator helper below. */
export const KNOWN_SESSION_KINDS = [SESSION_KIND_CHAT, SESSION_KIND_CHECKLIST] as const;

export type SessionKind = (typeof KNOWN_SESSION_KINDS)[number];

// ---- Tag conventions (mirrors backend ``TAG_GROUP_SEPARATOR``) ------------

/**
 * Slash-namespace separator on tag names — ``bearings/architect`` →
 * group ``bearings``, leaf ``architect``. Mirrors the backend's
 * :data:`bearings.config.constants.TAG_GROUP_SEPARATOR`.
 */
export const TAG_GROUP_SEPARATOR = "/";

// ---- UI strings ------------------------------------------------------------

/**
 * UI string table — pulled out of components per coding-standards
 * §"i18n-ready string tables". A future locale layer can swap the
 * record's values without touching component bodies. Keys are stable
 * identifiers; values are the English presentation strings.
 */
/**
 * Conversation-pane string table — chat.md §"opens an existing chat"
 * + §"What a message turn looks like" presentation strings, factored
 * out of components per coding-standards "i18n-ready string tables".
 */
export const CONVERSATION_STRINGS = {
  emptyTranscript: "No messages yet. Send one to start the turn.",
  loadingTranscript: "Loading conversation…",
  loadFailed: "Couldn't load the transcript.",
  toolDrawerLabel: "Tool calls",
  toolDrawerOpenLabel: "Open tool calls",
  toolDrawerCloseLabel: "Close tool calls",
  toolDrawerJumpLabel: "⤴ TOOLS",
  toolStatusOk: "Completed",
  toolStatusError: "Failed",
  toolStatusRunning: "Running",
  toolOutputExpand: "Show full output",
  toolOutputCollapse: "Collapse output",
  // Behavior doc §"Very-long-output truncation rules" — wording mirrors
  // backend STREAM_TRUNCATION_MARKER_TEMPLATE for visual consistency.
  truncationLabel: "[truncated — more bytes elided]",
  routingBadgeTooltipFallback: "Routing reason unavailable",
  pairedChatBreadcrumbPrefix: "↳",
  pairedChatBreadcrumbDeleted: "(checklist deleted)",
  pairedChatBreadcrumbAriaLabel: "Paired checklist breadcrumb",
  errorBubbleLabel: "Error",
  scrollToBottomLabel: "↓ Jump to bottom",
} as const;

/**
 * Soft display cap on a single tool-call's body. Behavior doc
 * (``docs/behavior/tool-output-streaming.md`` §"Very-long-output
 * truncation rules") prescribes a soft cap that folds the middle
 * inside an inline expander while keeping head/tail bookends visible.
 * Mirrors the backend ``DEFAULT_TOOL_OUTPUT_CAP_CHARS`` (8000) so the
 * UI cap and the persistence cap agree by default — a runaway tool
 * past the persistence hard cap (1 MiB) is also past this display
 * cap, so the UI's truncation marker only renders when the persisted
 * body itself is truncated.
 */
export const CHAT_TOOL_OUTPUT_SOFT_CAP_CHARS = 8000;

/**
 * ``rel`` attribute for outbound anchors per chat.md §"Conversation
 * rendering" — "rendered as anchors that open in a new tab with
 * ``noopener noreferrer``". Pulled out of the linkifier so a future
 * security review can grep one place rather than chasing call sites.
 */
export const CHAT_LINK_REL = "noopener noreferrer";

export const SIDEBAR_STRINGS = {
  heading: "Bearings",
  versionTag: "v0.18.0-dev",
  sessionsLabel: "Session list",
  tagFilterLabel: "Filter by tag",
  tagFilterClearLabel: "Clear filter",
  emptySessionList: "No sessions match the current filter.",
  emptySessionListUnfiltered: "No sessions yet.",
  loadingSessions: "Loading sessions…",
  loadFailed: "Couldn't load sessions.",
  ungroupedTagsLabel: "(ungrouped)",
  pinnedIndicatorAriaLabel: "Pinned",
  closedIndicatorAriaLabel: "Closed",
  errorPendingIndicatorAriaLabel: "Needs attention",
  kindIndicatorAriaLabels: {
    [SESSION_KIND_CHAT]: "Chat session",
    [SESSION_KIND_CHECKLIST]: "Checklist session",
  } as const satisfies Record<SessionKind, string>,
} as const;

// ---- Routing preview + quota guard tunings --------------------------------

/**
 * Debounce window for the new-session dialog's reactive routing
 * preview (spec §6 — "Typing in the first-message field re-evaluates
 * rules in real time (debounced ~300ms)"). Mirrors the backend's
 * :data:`bearings.config.constants.ROUTING_PREVIEW_DEBOUNCE_MS`
 * (``src/bearings/config/constants.py:65``); value duplicated rather
 * than synced because the backend module is Python-only.
 */
export const ROUTING_PREVIEW_DEBOUNCE_MS = 300;

/**
 * Quota-bar yellow / red transition thresholds (spec §4 + §10 —
 * "yellow at 80% used, red at 95%"). Mirrors the backend's
 * :data:`QUOTA_BAR_YELLOW_PCT` / :data:`QUOTA_BAR_RED_PCT`
 * (``src/bearings/config/constants.py:81-82``). Values are fractions
 * in ``[0.0, 1.0]`` so they line up with the
 * ``overall_used_pct`` / ``sonnet_used_pct`` shape on the API.
 */
export const QUOTA_BAR_YELLOW_PCT = 0.8;
export const QUOTA_BAR_RED_PCT = 0.95;

/**
 * Routing-source values mirrored from
 * :data:`bearings.config.constants.KNOWN_ROUTING_SOURCES` (spec §App
 * A enum). The dialog reads ``quota_downgrade`` to decide when to
 * render the downgrade banner with the "Use anyway" override;
 * InspectorRouting (item 2.6) reads every value to render the
 * source label inside "Why this model?".
 */
export const ROUTING_SOURCE_TAG_RULE = "tag_rule";
export const ROUTING_SOURCE_SYSTEM_RULE = "system_rule";
export const ROUTING_SOURCE_DEFAULT = "default";
export const ROUTING_SOURCE_MANUAL = "manual";
export const ROUTING_SOURCE_QUOTA_DOWNGRADE = "quota_downgrade";
export const ROUTING_SOURCE_MANUAL_OVERRIDE_QUOTA = "manual_override_quota";
export const ROUTING_SOURCE_UNKNOWN_LEGACY = "unknown_legacy";

/**
 * Full routing-source alphabet. Mirrors backend
 * :data:`bearings.config.constants.KNOWN_ROUTING_SOURCES` (spec §App
 * A). Iterated by the InspectorRouting "Why this model?" surface so
 * a future source addition lights up automatically.
 */
export const KNOWN_ROUTING_SOURCES = [
  ROUTING_SOURCE_TAG_RULE,
  ROUTING_SOURCE_SYSTEM_RULE,
  ROUTING_SOURCE_DEFAULT,
  ROUTING_SOURCE_MANUAL,
  ROUTING_SOURCE_QUOTA_DOWNGRADE,
  ROUTING_SOURCE_MANUAL_OVERRIDE_QUOTA,
  ROUTING_SOURCE_UNKNOWN_LEGACY,
] as const;
export type RoutingSource = (typeof KNOWN_ROUTING_SOURCES)[number];

// ---- Routing-rule CRUD endpoints (spec §9) ------------------------------

/**
 * ``GET /api/tags/{id}/routing`` / ``POST /api/tags/{id}/routing`` —
 * tag-rule list + create surfaces consumed by
 * :class:`RoutingRuleEditor` (item 2.8) per spec §9. Mirrors
 * :func:`bearings.web.routes.routing.list_tag_rules` /
 * :func:`create_tag_rule`.
 */
export const tagRoutingRulesEndpoint = (tagId: number): string =>
  `${API_BASE}/tags/${tagId}/routing`;

/**
 * ``PATCH /api/routing/{id}`` / ``DELETE /api/routing/{id}`` — tag-rule
 * update + delete surfaces (spec §9). The backend reserves
 * ``PATCH /api/routing/system/{id}`` for system rules (item 1.8
 * decided-and-documented).
 */
export const tagRoutingRuleEndpoint = (ruleId: number): string => `${API_BASE}/routing/${ruleId}`;

/**
 * ``PATCH /api/tags/{id}/routing/reorder`` — re-stamp tag-rule
 * priorities to match the supplied id order (spec §9).
 */
export const tagRoutingReorderEndpoint = (tagId: number): string =>
  `${API_BASE}/tags/${tagId}/routing/reorder`;

/**
 * ``GET /api/routing/system`` / ``POST /api/routing/system`` —
 * system-rule list + create surfaces (spec §9).
 */
export const API_SYSTEM_ROUTING_RULES_ENDPOINT = `${API_BASE}/routing/system`;

/**
 * ``PATCH /api/routing/system/{id}`` / ``DELETE …`` — system-rule
 * update + delete surfaces (spec §9). Spec §9 does NOT enumerate a
 * dedicated system-rule reorder endpoint; the editor re-stamps
 * priorities by issuing per-rule PATCHes (decided-and-documented in
 * :class:`RoutingRuleEditor`).
 */
export const systemRoutingRuleEndpoint = (ruleId: number): string =>
  `${API_BASE}/routing/system/${ruleId}`;

// ---- Routing match-type alphabet (mirrors backend) -----------------------

/**
 * Match-type alphabet per spec §3:
 *
 * - ``keyword`` — case-insensitive substring against the first user
 *   message; ``match_value`` is comma-separated; any match triggers.
 * - ``regex`` — ``re.IGNORECASE`` regex against the first user
 *   message. Invalid regex disables the rule (spec §3 "Invalid
 *   regexes disable the rule and surface an error in the editor").
 * - ``length_gt`` / ``length_lt`` — message length in characters
 *   compared against ``int(match_value)``.
 * - ``always`` — unconditional; used as the lowest-priority fallback
 *   in system rules (priority 1000 in the seeded set per spec §3).
 *
 * Values mirror the backend
 * :data:`bearings.config.constants.KNOWN_ROUTING_MATCH_TYPES` (spec
 * §3 schema CHECK constraint). Drift between the two surfaces is a
 * behavioural bug caught by the backend's ``CHECK`` clause the first
 * time a rule of an unknown type reaches the route.
 */
export const ROUTING_MATCH_TYPE_KEYWORD = "keyword";
export const ROUTING_MATCH_TYPE_REGEX = "regex";
export const ROUTING_MATCH_TYPE_LENGTH_GT = "length_gt";
export const ROUTING_MATCH_TYPE_LENGTH_LT = "length_lt";
export const ROUTING_MATCH_TYPE_ALWAYS = "always";
export const KNOWN_ROUTING_MATCH_TYPES = [
  ROUTING_MATCH_TYPE_KEYWORD,
  ROUTING_MATCH_TYPE_REGEX,
  ROUTING_MATCH_TYPE_LENGTH_GT,
  ROUTING_MATCH_TYPE_LENGTH_LT,
  ROUTING_MATCH_TYPE_ALWAYS,
] as const;
export type RoutingMatchType = (typeof KNOWN_ROUTING_MATCH_TYPES)[number];

/**
 * Rule-kind discriminator for the ``RoutingRuleEditor`` ``kind`` prop
 * — the editor branches on this to pick the tag-rule vs system-rule
 * endpoint set. Mirrors the ``rule_kind`` column on
 * :class:`OverrideRateOut` (item 1.8 override-rate aggregator).
 *
 * The full alphabet (``ROUTING_RULE_KIND_SYSTEM``,
 * ``KNOWN_ROUTING_RULE_KINDS``, ``RoutingRuleKind``) is deliberately
 * not re-exported in v1 — the editor's ``Props`` union is the single
 * consumer of the system-side discriminant and binds the literal
 * ``"system"`` directly. The full alphabet returns when a second
 * consumer (a kind-aware filter, a future API client) needs it.
 */
export const ROUTING_RULE_KIND_TAG = "tag";

/**
 * Default ``priority`` for a freshly added rule. Mirrors the backend
 * column defaults (``DEFAULT 100`` on tag rules, ``DEFAULT 1000`` on
 * system rules) per spec §3 schema. Tag rules pack at 100; new
 * system rules slot at 500 — between the seeded keyword/length rules
 * (10–60) and the ``always`` fallback (1000) so user-added rules
 * appear neither at the very top nor below the workhorse default.
 */
export const ROUTING_RULE_DEFAULT_PRIORITY_TAG = 100;
export const ROUTING_RULE_DEFAULT_PRIORITY_SYSTEM = 500;

/**
 * Default ``advisor_max_uses`` for a freshly added rule (mirrors
 * spec §2 default-policy table — Sonnet executor, the rule editor's
 * starting executor → 5 advisor calls). Backend default is also 5
 * via the ``advisor_max_uses INTEGER DEFAULT 5`` column on both rule
 * tables (spec §3 schema).
 */
export const ROUTING_RULE_DEFAULT_ADVISOR_MAX_USES = 5;

// ---- Routing-rule editor strings (spec §3 + §10) ------------------------

/**
 * UI strings for :class:`RoutingRuleEditor` + :class:`RuleRow` +
 * :class:`TestAgainstMessageDialog` (item 2.8). Cites spec §3 (rule
 * editing surface) + §10 ("Modified: Routing rule editor" widget +
 * the deterministic "Test against message" dialog) + §8 ("Review:"
 * highlight prefix on rules whose override rate exceeds
 * :data:`OVERRIDE_RATE_REVIEW_THRESHOLD`).
 *
 * Pulled out of components per coding-standards
 * §"i18n-ready string tables".
 */
export const ROUTING_EDITOR_STRINGS = {
  // Top-level pane labels (spec §10 "Modified: Routing rule editor").
  paneAriaLabelTag: "Tag routing rules",
  paneAriaLabelSystem: "System routing rules",
  headingTag: "Tag routing rules",
  headingSystem: "System routing rules",
  loading: "Loading routing rules…",
  loadFailed: "Couldn't load routing rules.",
  saveFailed: "Couldn't save the rule.",
  reorderFailed: "Couldn't reorder rules.",
  emptyTag: "No tag rules yet — add one to override the system defaults.",
  emptySystem: "No system rules yet — add one as a global fallback.",
  addRuleLabel: "Add rule",
  // Per spec §8: "Rules with override_rate > 0.30 over the last 14 days
  // are surfaced in the routing rule editor as 'Review:' highlighted
  // rows." The prefix is the literal string the spec calls out.
  reviewPrefix: "Review:",
  reviewTooltipTemplate: "Override rate {pct}% over the last {days} days — review this rule.",
  // Per-row column labels (spec §10 row layout — priority, match-type,
  // match-value, executor, advisor, enabled, effort, reason).
  rowAriaLabelTemplate: "Routing rule {ruleId}",
  rowDragHandleAriaLabel: "Drag to reorder",
  rowPriorityLabel: "Priority",
  rowMatchTypeLabel: "Match",
  rowMatchValueLabel: "Value",
  rowMatchValuePlaceholderKeyword: "comma-separated keywords",
  rowMatchValuePlaceholderRegex: "case-insensitive regex",
  rowMatchValuePlaceholderLength: "length threshold (chars)",
  rowMatchValueDisabledAlways: "(no value — always matches)",
  rowMatchValueInvalidRegex: "Invalid regex — rule disabled until fixed.",
  rowExecutorLabel: "Executor",
  rowAdvisorLabel: "Advisor",
  rowAdvisorMaxUsesLabel: "Max calls",
  rowEffortLabel: "Effort",
  rowReasonLabel: "Reason",
  rowReasonPlaceholder: "Explain why this rule fires (shown in UI when matched).",
  rowEnabledLabel: "Enabled",
  rowSeededIndicatorLabel: "Seeded",
  rowSeededIndicatorTitle: "Shipped default rule — disable rather than delete.",
  // Per-row action labels (spec §10 "Right-click ⋮: Test against
  // message, Duplicate, Disable, Delete").
  actionTestLabel: "Test against message",
  actionDuplicateLabel: "Duplicate",
  actionDisableLabel: "Disable",
  actionEnableLabel: "Enable",
  actionDeleteLabel: "Delete",
  actionDeleteConfirmTemplate: "Delete this rule? This cannot be undone.",
  actionMenuAriaLabel: "Rule actions",
  // Test-against-message dialog (spec §10: "deterministic dialog —
  // it evaluates the rule's match condition against pasted text and
  // shows the resulting routing decision. No LLM call. Test inputs
  // are not stored").
  testDialogTitle: "Test against message",
  testDialogAriaLabel: "Test rule against message",
  testDialogIntro:
    "Paste a message to evaluate against this rule. The check runs locally — no LLM, no save.",
  testDialogMessageLabel: "Message",
  testDialogMessagePlaceholder: "Paste the first user message here…",
  testDialogEvaluateLabel: "Evaluate",
  testDialogCloseLabel: "Close",
  testDialogResultMatched: "Rule matched.",
  testDialogResultMissed: "Rule did not match.",
  testDialogResultExecutorLabel: "Would route to executor",
  testDialogResultAdvisorLabel: "Advisor",
  testDialogResultEffortLabel: "Effort",
  testDialogResultReasonLabel: "Reason",
  testDialogInvalidRegex: "Invalid regex — fix the rule before testing.",
  // Match-type display labels (spec §3 alphabet → user-visible).
  matchTypeLabels: {
    [ROUTING_MATCH_TYPE_KEYWORD]: "keyword",
    [ROUTING_MATCH_TYPE_REGEX]: "regex",
    [ROUTING_MATCH_TYPE_LENGTH_GT]: "length >",
    [ROUTING_MATCH_TYPE_LENGTH_LT]: "length <",
    [ROUTING_MATCH_TYPE_ALWAYS]: "always",
  } as const satisfies Record<RoutingMatchType, string>,
} as const;

// ---- Inspector usage / override-rate windows + thresholds ----------------

/**
 * InspectorUsage headroom-chart window (spec §7 "Quota efficiency" +
 * §10 "Headroom remaining chart" — "rolling 7-day plot of overall
 * bucket and Sonnet bucket consumption, with reset markers").
 * Mirrors backend :data:`USAGE_HEADROOM_WINDOW_DAYS` in
 * ``src/bearings/config/constants.py:97`` so the chart range and the
 * ``GET /api/quota/history?days=N`` default agree.
 */
export const USAGE_HEADROOM_WINDOW_DAYS = 7;

/**
 * Override-rate "Review:" threshold (spec §8 — "Rules with
 * override_rate > 0.30 over the last 14 days are surfaced ... as
 * 'Review:' highlighted rows" + §10 "Rules to review list — rules
 * with override rate > 30 % in the last 14 days, click to jump to
 * the rule editor"). Mirrors backend
 * :data:`OVERRIDE_RATE_REVIEW_THRESHOLD` in
 * ``src/bearings/config/constants.py:87``.
 */
export const OVERRIDE_RATE_REVIEW_THRESHOLD = 0.3;

/**
 * Override-rate rolling window (spec §8 + §10). Mirrors backend
 * :data:`OVERRIDE_RATE_WINDOW_DAYS` in
 * ``src/bearings/config/constants.py:92``.
 */
export const OVERRIDE_RATE_WINDOW_DAYS = 14;

// ---- Routing alphabet (mirrors backend ``KNOWN_*``) -----------------------

/**
 * Two-axis routing selector alphabets per spec §3 (rule eval inputs)
 * + §6 (the new-session dialog selectors). Mirrors the backend's
 * :data:`KNOWN_EXECUTOR_MODELS` and :data:`KNOWN_EFFORT_LEVELS`
 * (``src/bearings/config/constants.py:224, 236``). The
 * advisor-axis null choice is encoded as
 * :const:`ADVISOR_MODEL_NONE` so a templated ``<select>`` carries it
 * without a sentinel literal.
 */
export const EXECUTOR_MODEL_SONNET = "sonnet";
export const EXECUTOR_MODEL_HAIKU = "haiku";
export const EXECUTOR_MODEL_OPUS = "opus";
export const KNOWN_EXECUTOR_MODELS = [
  EXECUTOR_MODEL_SONNET,
  EXECUTOR_MODEL_HAIKU,
  EXECUTOR_MODEL_OPUS,
] as const;
export type ExecutorModel = (typeof KNOWN_EXECUTOR_MODELS)[number];

export const ADVISOR_MODEL_OPUS = "opus";
export const ADVISOR_MODEL_NONE = "" as const;
export const KNOWN_ADVISOR_MODELS = [ADVISOR_MODEL_NONE, ADVISOR_MODEL_OPUS] as const;
export type AdvisorModelChoice = (typeof KNOWN_ADVISOR_MODELS)[number];

export const EFFORT_LEVEL_AUTO = "auto";
const EFFORT_LEVEL_LOW = "low";
const EFFORT_LEVEL_MEDIUM = "medium";
const EFFORT_LEVEL_HIGH = "high";
const EFFORT_LEVEL_XHIGH = "xhigh";
export const KNOWN_EFFORT_LEVELS = [
  EFFORT_LEVEL_AUTO,
  EFFORT_LEVEL_LOW,
  EFFORT_LEVEL_MEDIUM,
  EFFORT_LEVEL_HIGH,
  EFFORT_LEVEL_XHIGH,
] as const;
export type EffortLevel = (typeof KNOWN_EFFORT_LEVELS)[number];

/**
 * Default ``advisor.max_uses`` for the new-session dialog (spec §2
 * "Default policy" table — Sonnet executor → 5, Haiku executor → 3,
 * Opus executor → no advisor). Mirrors backend
 * :data:`DEFAULT_ADVISOR_MAX_USES_SONNET` /
 * :data:`DEFAULT_ADVISOR_MAX_USES_HAIKU`.
 */
export const DEFAULT_ADVISOR_MAX_USES_SONNET = 5;
export const DEFAULT_ADVISOR_MAX_USES_HAIKU = 3;

// ---- Inspector tab alphabet + string table -------------------------------

/**
 * Inspector subsection identifiers — the tab strip on
 * :class:`Inspector` (right column of the app shell, per
 * ``docs/architecture-v1.md`` §1.2 inspector decomposition) renders
 * one button per id.
 *
 * Item 2.5 ships the first three (Agent / Context / Instructions);
 * item 2.6 lights up Routing / Usage by populating their bodies and
 * extending :data:`KNOWN_INSPECTOR_TABS`. The IDs themselves live here
 * so the shell never refers to a tab by inline string literal — a new
 * id is added by editing this file, not by patching the shell.
 *
 * The values are stable wire-shaped strings (lowercase ASCII, no
 * whitespace) so a future ``?inspector_tab=<id>`` deep-link or a
 * keyboard-shortcut binding can address a tab without a translation
 * table.
 */
export const INSPECTOR_TAB_AGENT = "agent";
export const INSPECTOR_TAB_CONTEXT = "context";
export const INSPECTOR_TAB_INSTRUCTIONS = "instructions";
/**
 * Routing subsection (spec §10 "Modified: Inspector 'Routing'
 * subsection"). Lit by item 2.6 — the Inspector shell switches on
 * the id to render :class:`InspectorRouting`.
 */
export const INSPECTOR_TAB_ROUTING = "routing";
/**
 * Usage subsection (spec §10 "New: Usage tab in the inspector").
 * Lit by item 2.6 — the Inspector shell switches on the id to
 * render :class:`InspectorUsage`.
 */
export const INSPECTOR_TAB_USAGE = "usage";

/**
 * Tabs the inspector exposes. Item 2.6 appended ``"routing"`` and
 * ``"usage"`` (per spec §10 inspector decomposition) — the shell's
 * body switch grew two cases; the tab strip itself iterates this
 * tuple so the new tabs appear without further refactor.
 */
export const KNOWN_INSPECTOR_TABS = [
  INSPECTOR_TAB_AGENT,
  INSPECTOR_TAB_CONTEXT,
  INSPECTOR_TAB_INSTRUCTIONS,
  INSPECTOR_TAB_ROUTING,
  INSPECTOR_TAB_USAGE,
] as const;
export type InspectorTabId = (typeof KNOWN_INSPECTOR_TABS)[number];

/**
 * Default tab the inspector lands on when the user first selects a
 * session. ``Agent`` is chosen because it is the only subsection whose
 * surface (executor model, working dir) the user already saw mirrored
 * in the conversation header — opening on ``Agent`` is a natural
 * continuation, not a context switch.
 *
 * The default is a constant rather than a runtime preference because
 * theme-style per-device persistence is item 2.9's surface; v1 of the
 * inspector uses an in-memory selection that resets across reloads.
 *
 * The literal value mirrors :const:`INSPECTOR_TAB_AGENT` deliberately —
 * the same string carries two distinct meanings (the *id* of the agent
 * tab vs the *default* the inspector boots into), and the constants
 * stay separate so a future change to the default can flip this one
 * value without re-pointing every reference to ``INSPECTOR_TAB_AGENT``
 * (which is the agent tab's identity, not the default policy). The
 * type cast keeps knip from flagging the literal as a structural
 * duplicate of the other ``"agent"`` export.
 */
export const DEFAULT_INSPECTOR_TAB = "agent" as InspectorTabId;

/**
 * Inspector string table — chat.md §"opens an existing chat" cites
 * the inspector as a sibling pane to the conversation; chat.md
 * §"What the user does NOT see in chat" enumerates Routing + Usage
 * as inspector subsections and cross-references the per-message
 * timeline.  chat.md is silent on the user-facing copy of the
 * Agent / Context / Instructions subsections — implementation here
 * follows the architecture-v1.md §1.2 decomposition (one component
 * per subsection) plus the ``SessionOut`` shape from
 * ``api/sessions.ts`` for the field labels. Behavioral gap recorded
 * in the executor's self-verification block per plan
 * §"Behavioral gap escalation".
 */
export const INSPECTOR_STRINGS = {
  paneAriaLabel: "Inspector",
  tabStripAriaLabel: "Inspector subsections",
  emptySession: "Select a session to inspect.",
  missingSession: "The selected session is no longer loaded — pick another from the sidebar.",
  tabLabels: {
    [INSPECTOR_TAB_AGENT]: "Agent",
    [INSPECTOR_TAB_CONTEXT]: "Context",
    [INSPECTOR_TAB_INSTRUCTIONS]: "Instructions",
    [INSPECTOR_TAB_ROUTING]: "Routing",
    [INSPECTOR_TAB_USAGE]: "Usage",
  } as const satisfies Record<InspectorTabId, string>,
  // Agent subsection — exposes the active session's agent config.
  // Items 2.6 + 1.8 add advisor / effort / fallback fields by widening
  // ``SessionOut`` and surfacing the new columns here.
  agentHeading: "Agent",
  agentModelLabel: "Executor model",
  agentPermissionModeLabel: "Permission mode",
  agentPermissionModeUnset: "(default)",
  agentWorkingDirLabel: "Working directory",
  agentMaxBudgetLabel: "Budget cap (USD)",
  agentMaxBudgetUnset: "no cap",
  agentTotalCostLabel: "Total cost (USD)",
  agentMessageCountLabel: "Messages",
  // Context subsection — mirrors the context-window / cost data the
  // header band carries (chat.md §"opens an existing chat") in the
  // inspector's longer-form layout. The system-prompt + tag-default
  // overlays + vault attachments parts of the Context subsection are
  // gated on items 1.4 / 1.5 / 1.7 surfacing the assembled context
  // over the API; rendered here as a placeholder section so 2.5 ships
  // a complete shell.
  contextHeading: "Context",
  contextSessionTitleLabel: "Title",
  contextDescriptionLabel: "Description",
  contextDescriptionEmpty: "(no description)",
  contextLastContextPctLabel: "Last context-window pressure",
  contextLastContextTokensLabel: "Last context tokens",
  contextLastContextMaxLabel: "Context-window max",
  contextLastContextNotSeen: "no turn observed yet",
  contextAssembledHeading: "Assembled context",
  contextAssembledPlaceholder:
    "System prompt, tag-default overlays, and vault attachments surface here once the assembled-context API lands (items 1.4 / 1.5 / 1.7).",
  // Instructions subsection — exposes ``session_instructions`` from
  // the SessionOut shape. ``null`` / empty renders the empty-state copy.
  instructionsHeading: "Instructions",
  instructionsBodyLabel: "Session instructions",
  instructionsEmpty: "No per-session instructions set.",
  // Routing subsection (spec §10 "Modified: Inspector 'Routing'
  // subsection"). The current-decision card surfaces the four
  // routing-decision fields the spec lists; the timeline + advisor
  // totals + quota delta read the per-message routing/usage projection
  // from item 1.9. The "Why this model?" expandable per assistant
  // message renders the rule eval chain (source + matched_rule_id +
  // reason) — the full ``evaluated_rules`` list is a future widening
  // (item 1.9 surfaces ``matched_rule_id`` only on the wire today).
  routingHeading: "Routing",
  routingLoading: "Loading routing data…",
  routingError: "Couldn't load routing data.",
  routingEmpty: "No assistant turns yet — routing data appears after the first reply.",
  routingCurrentHeading: "Current routing",
  routingCurrentExecutorLabel: "Executor",
  routingCurrentAdvisorLabel: "Advisor",
  routingCurrentAdvisorNone: "(none)",
  routingCurrentEffortLabel: "Effort",
  routingCurrentSourceLabel: "Source",
  routingCurrentReasonLabel: "Reason",
  routingTotalsHeading: "Session totals",
  routingTotalsAdvisorCallsLabel: "Advisor calls",
  routingTotalsAdvisorTokensLabel: "Advisor tokens",
  routingTotalsExecutorTokensLabel: "Executor tokens",
  routingQuotaDeltaHeading: "Quota delta this session",
  routingQuotaDeltaOverallLabel: "Overall bucket",
  routingQuotaDeltaSonnetLabel: "Sonnet bucket",
  routingTimelineHeading: "Per-message timeline",
  routingTimelineEmpty: "No assistant messages with routing data yet.",
  routingTimelineWhyLabel: "Why this model?",
  routingTimelineMatchedRuleLabel: "Matched rule",
  routingTimelineNoMatchedRule: "(no rule — fallback default)",
  // Routing-source presentation labels (spec §App A enum). Mirror the
  // wire alphabet via :const:`KNOWN_ROUTING_SOURCES`.
  routingSourceLabels: {
    [ROUTING_SOURCE_TAG_RULE]: "Tag rule",
    [ROUTING_SOURCE_SYSTEM_RULE]: "System rule",
    [ROUTING_SOURCE_DEFAULT]: "Default",
    [ROUTING_SOURCE_MANUAL]: "Manual",
    [ROUTING_SOURCE_QUOTA_DOWNGRADE]: "Quota downgrade",
    [ROUTING_SOURCE_MANUAL_OVERRIDE_QUOTA]: "Manual override (quota)",
    [ROUTING_SOURCE_UNKNOWN_LEGACY]: "Unknown (legacy)",
  } as const satisfies Record<RoutingSource, string>,
  // Usage subsection (spec §10 "New: Usage tab in the inspector").
  // Strings match the four widgets the spec enumerates: headroom
  // chart, by-model table, advisor-effectiveness widget, rules-to-
  // review list.
  usageHeading: "Usage",
  usageLoading: "Loading usage data…",
  usageError: "Couldn't load usage data.",
  usageHeadroomHeading: "Headroom remaining",
  usageHeadroomCaption: "Rolling 7-day plot of overall + Sonnet bucket consumption.",
  usageHeadroomEmpty: "No quota snapshots in the last 7 days.",
  usageHeadroomOverallLabel: "Overall",
  usageHeadroomSonnetLabel: "Sonnet",
  usageHeadroomCapturedAtLabel: "Captured at",
  usageByModelHeading: "By model",
  usageByModelEmpty: "No per-model token totals in the last 7 days.",
  usageByModelColModel: "Model",
  usageByModelColRole: "Role",
  usageByModelColInputTokens: "Input",
  usageByModelColOutputTokens: "Output",
  usageByModelColAdvisorCalls: "Advisor calls",
  usageByModelColCacheReadTokens: "Cache read",
  usageByModelColSessions: "Sessions",
  usageAdvisorEffectivenessHeading: "Advisor effectiveness",
  usageAdvisorEffectivenessEmpty:
    "Not enough data — the advisor effectiveness widget needs at least one session with advisor calls.",
  usageAdvisorEffectivenessCallsPerSessionLabel: "Calls per session",
  usageAdvisorEffectivenessShareLabel: "Advisor token share",
  usageAdvisorEffectivenessQualReadLabel: "Read",
  usageAdvisorEffectivenessQualPulling: "Advisor is pulling its weight.",
  usageAdvisorEffectivenessQualMarginal: "Advisor contribution is marginal.",
  usageAdvisorEffectivenessQualUnused: "Advisor is rarely consulted.",
  usageRulesToReviewHeading: "Rules to review",
  usageRulesToReviewCaption: "Rules whose override rate exceeded 30% over the last 14 days.",
  usageRulesToReviewEmpty: "No rules over the review threshold — routing is healthy.",
  usageRulesToReviewColKind: "Kind",
  usageRulesToReviewColRuleId: "Rule",
  usageRulesToReviewColRate: "Override rate",
  usageRulesToReviewColFired: "Fired",
  usageRulesToReviewColOverridden: "Overridden",
} as const;

// ---- New-session dialog string table -------------------------------------

/**
 * UI strings for the new-session dialog (chat.md §"creates a chat" +
 * spec §6 layout + spec §8 quota banner copy). Pulled out of the
 * components per coding-standards §"i18n-ready string tables".
 */
export const NEW_SESSION_STRINGS = {
  dialogTitle: "New Session",
  dialogAriaLabel: "New session dialog",
  routingHeading: "Routing (auto-resolved from tags + first message)",
  executorLabel: "Executor",
  advisorLabel: "Advisor",
  advisorEnabledLabel: "enabled",
  advisorMaxUsesLabel: "max calls",
  advisorOpusExecutorHint: "Opus is the executor — advisor not needed.",
  advisorOptionNoneLabel: "(none)",
  effortLabel: "Effort",
  routedFromPrefix: "Routed from",
  routedManualOverride: "Manual override",
  firstMessageLabel: "First message",
  firstMessagePlaceholder: "What would you like to start the session with?",
  quotaHeading: "Quota",
  quotaOverallLabel: "overall",
  quotaSonnetLabel: "sonnet",
  quotaUnavailable: "Quota data unavailable",
  quotaResetTooltipPrefix: "Resets at",
  downgradeBannerPrefix: "Routing downgraded to",
  downgradeBannerOverallSuffixTemplate: "(overall quota at {pct}%)",
  downgradeBannerSonnetSuffixTemplate: "(sonnet quota at {pct}%)",
  downgradeUseAnywayLabel: "Use {model} anyway",
  cancelLabel: "Cancel",
  submitLabel: "Start Session",
  loadingPreview: "Resolving routing…",
  previewError: "Couldn't resolve routing — try again.",
  // Display labels for executor / advisor / effort options. Capitalised
  // for the dropdown surface; the underlying value is the lowercase
  // wire identifier (``sonnet`` / ``haiku`` / ``opus`` / ``auto`` /
  // ``low`` / ``medium`` / ``high`` / ``xhigh``).
  executorLabels: {
    [EXECUTOR_MODEL_SONNET]: "Sonnet 4.6",
    [EXECUTOR_MODEL_HAIKU]: "Haiku 4.5",
    [EXECUTOR_MODEL_OPUS]: "Opus 4.7",
  } as const satisfies Record<ExecutorModel, string>,
  advisorLabels: {
    [ADVISOR_MODEL_NONE]: "(none)",
    [ADVISOR_MODEL_OPUS]: "Opus 4.6",
  } as const satisfies Record<AdvisorModelChoice, string>,
  effortLabels: {
    [EFFORT_LEVEL_AUTO]: "auto",
    [EFFORT_LEVEL_LOW]: "low",
    [EFFORT_LEVEL_MEDIUM]: "medium",
    [EFFORT_LEVEL_HIGH]: "high",
    [EFFORT_LEVEL_XHIGH]: "xhigh",
  } as const satisfies Record<EffortLevel, string>,
} as const;

// ---- Checklist alphabets (mirrors backend ``KNOWN_*``) --------------------

/**
 * Auto-driver run-state alphabet — mirrors backend
 * :data:`bearings.config.constants.KNOWN_AUTO_DRIVER_STATES`. The
 * AutoDriverControls component branches on the active run's
 * ``state`` to enable / disable the run-control buttons per
 * ``docs/behavior/checklists.md`` §"Run-control surface".
 */
export const AUTO_DRIVER_STATE_IDLE = "idle";
export const AUTO_DRIVER_STATE_RUNNING = "running";
export const AUTO_DRIVER_STATE_PAUSED = "paused";
export const AUTO_DRIVER_STATE_FINISHED = "finished";
// ``errored`` + the full alphabet (``KNOWN_AUTO_DRIVER_STATES``) +
// the ``AutoDriverState`` type are deliberately not exported in v1 —
// the only consumer (AutoDriverControls) reads the four states above
// directly. The backend alphabet (``KNOWN_AUTO_DRIVER_STATES`` in
// :mod:`bearings.config.constants`) stays the source of truth; this
// file re-introduces the mirror when an enum-shaped UI consumer
// arrives.

/**
 * Auto-driver failure-policy alphabet — mirrors backend
 * :data:`bearings.config.constants.KNOWN_AUTO_DRIVER_FAILURE_POLICIES`.
 * The user picks one in the AutoDriverControls dropdown before pressing
 * Start; the choice applies to the next run only.
 */
export const AUTO_DRIVER_FAILURE_POLICY_HALT = "halt";
export const AUTO_DRIVER_FAILURE_POLICY_SKIP = "skip";
export const KNOWN_AUTO_DRIVER_FAILURE_POLICIES = [
  AUTO_DRIVER_FAILURE_POLICY_HALT,
  AUTO_DRIVER_FAILURE_POLICY_SKIP,
] as const;
export type AutoDriverFailurePolicy = (typeof KNOWN_AUTO_DRIVER_FAILURE_POLICIES)[number];

/**
 * Item non-completion category alphabet — mirrors backend
 * :data:`bearings.config.constants.KNOWN_ITEM_OUTCOMES`. Drives the pip
 * color in :class:`SentinelEvent` per
 * ``docs/behavior/checklists.md`` §"Item-status colors".
 */
export const ITEM_OUTCOME_BLOCKED = "blocked";
export const ITEM_OUTCOME_FAILED = "failed";
export const ITEM_OUTCOME_SKIPPED = "skipped";
export const KNOWN_ITEM_OUTCOMES = [
  ITEM_OUTCOME_BLOCKED,
  ITEM_OUTCOME_FAILED,
  ITEM_OUTCOME_SKIPPED,
] as const;
// ``ItemOutcome`` type is not yet referenced by a TS consumer; the
// alphabet is read at runtime via the array. The type is re-introduced
// when a consumer needs the union form.

/**
 * Sentinel-kind alphabet — mirrors backend
 * :data:`bearings.config.constants.KNOWN_SENTINEL_KINDS`. Used by the
 * frontend sentinel parser (``parseSentinels`` in ``sentinel.ts``) to
 * decide which kinds are well-known and which to ignore as malformed
 * per ``docs/behavior/checklists.md`` §"Sentinels".
 */
export const SENTINEL_KIND_ITEM_DONE = "item_done";
export const SENTINEL_KIND_HANDOFF = "handoff";
export const SENTINEL_KIND_FOLLOWUP_BLOCKING = "followup_blocking";
export const SENTINEL_KIND_FOLLOWUP_NONBLOCKING = "followup_nonblocking";
export const SENTINEL_KIND_ITEM_BLOCKED = "item_blocked";
export const SENTINEL_KIND_ITEM_FAILED = "item_failed";
export const KNOWN_SENTINEL_KINDS = [
  SENTINEL_KIND_ITEM_DONE,
  SENTINEL_KIND_HANDOFF,
  SENTINEL_KIND_FOLLOWUP_BLOCKING,
  SENTINEL_KIND_FOLLOWUP_NONBLOCKING,
  SENTINEL_KIND_ITEM_BLOCKED,
  SENTINEL_KIND_ITEM_FAILED,
] as const;
export type SentinelKind = (typeof KNOWN_SENTINEL_KINDS)[number];

/**
 * Spawned-by alphabet for a paired-chat link — mirrors backend
 * :data:`bearings.config.constants.KNOWN_PAIRED_CHAT_SPAWNED_BY`. The
 * link/spawn UI passes ``"user"``; the auto-driver passes
 * ``"driver"`` from server-side code paths only.
 */
export const PAIRED_CHAT_SPAWNED_BY_USER = "user";
// ``PAIRED_CHAT_SPAWNED_BY_DRIVER`` is the backend's enum value for
// auto-driver-spawned chats. The UI never sets it (only the user
// path), but the constant ships in the backend alphabet
// :data:`bearings.config.constants.KNOWN_PAIRED_CHAT_SPAWNED_BY` and
// is re-introduced here when a UI consumer needs to disambiguate the
// two paths.

/**
 * Driver outcome strings observed by the user when the status line
 * freezes — mirrors backend :data:`DRIVER_OUTCOME_*`. The empty-run
 * string is the only outcome the AutoDriverControls fallback path
 * needs today; the others (``Completed`` / ``Halted: max items`` /
 * ``Halted: stopped by user``) are backend-written values that arrive
 * through ``AutoDriverRunOut.outcome`` and are rendered verbatim by
 * :func:`formatStatusLine`.
 */
export const DRIVER_OUTCOME_HALTED_EMPTY = "Halted: empty";

/**
 * Auto-driver run-status poll cadence (ms). Decided-and-documented:
 * ``docs/behavior/checklists.md`` §"Run-control surface" prescribes a
 * live status line ("Running — item 3 of 12, leg 1, 0 failures") that
 * ticks while a run is in flight. Item 1.6 ships the run-row state +
 * the ``GET /api/checklists/{id}`` overview but NOT a per-checklist
 * driver-state WS broker; a future item adds the broker. v1 polls the
 * overview while a run is live so the user observes the status-line
 * ticks. 1500 ms chosen to match the user-perceived liveness of the
 * existing per-session WS heartbeat (``WS_IDLE_PING_INTERVAL_S=15``)
 * scaled for a UI thread that wants finer granularity than the
 * heartbeat-grade keepalive.
 */
export const CHECKLIST_OVERVIEW_POLL_INTERVAL_MS = 1500;

// ---- Checklist string table ----------------------------------------------

/**
 * UI string table for the checklist surfaces (item 2.7). Pulled out of
 * components per coding-standards §"i18n-ready string tables". Anchors
 * for each string trace to behavior docs in inline comments.
 */
export const CHECKLIST_STRINGS = {
  // Top-level pane labels (behavior/checklists.md §"What a checklist is, observably").
  paneAriaLabel: "Checklist pane",
  loadingOverview: "Loading checklist…",
  loadFailed: "Couldn't load this checklist.",
  emptyChecklist: "No items yet — type below to add the first one.",
  addItemPlaceholder: "Add an item…",
  addItemAriaLabel: "Add a new checklist item",
  // Item row labels (behavior/checklists.md §"Item edit / add / delete / reorder").
  itemDragHandleAriaLabel: "Drag to reorder",
  itemCheckboxAriaLabel: "Mark item complete",
  itemCheckboxParentDisabledTitle: "Parent items are derived from their children",
  itemLabelEditAriaLabel: "Edit item label",
  itemNotesToggleLabel: "Notes",
  itemNotesPlaceholder: "Add notes for this item…",
  itemDeleteLabel: "Delete",
  itemDeleteConfirmTemplate: "Delete this item? Children + paired chats will also be removed.",
  // Paired-chat link/spawn labels (behavior/paired-chats.md §"Link / spawn UI").
  pairedChatWorkOnThisLabel: "💬 Work on this",
  pairedChatWorkOnThisAriaLabel: "Spawn a paired chat for this item",
  pairedChatContinueLabel: "Continue working",
  pairedChatContinueAriaLabel: "Open the paired chat for this item",
  pairedChatLinkExistingLabel: "Link existing chat…",
  pairedChatUnlinkLabel: "Unlink chat",
  pairedChatLinkChooseLabel: "Choose a chat to link:",
  pairedChatLinkConfirmLabel: "Link",
  pairedChatLinkCancelLabel: "Cancel",
  pairedChatLinkEmptyLabel: "No open chat sessions to link.",
  pairedChatSpawnFailed: "Couldn't spawn a paired chat.",
  pairedChatLinkFailed: "Couldn't link the chosen chat.",
  // Auto-driver run-control labels (behavior/checklists.md §"Run-control surface").
  runControlsAriaLabel: "Auto-driver run controls",
  runStartLabel: "Start",
  runStopLabel: "Stop",
  runPauseLabel: "Pause",
  runResumeLabel: "Resume",
  runSkipCurrentLabel: "Skip current",
  runFailurePolicyLabel: "On failure",
  runFailurePolicyHaltLabel: "halt run",
  runFailurePolicySkipLabel: "skip & continue",
  runVisitExistingLabel: "Visit existing chats",
  runVisitExistingTitle: "Reuse each item's already-paired chat instead of spawning fresh ones.",
  runStatusIdle: "Idle — press Start to drive the checklist.",
  runStatusEmpty: "Halted: empty",
  // Behavior doc §"Run-control surface" template:
  // "Running — item N of M, leg L, F failures".
  runStatusRunningTemplate:
    "Running — item {currentIndex} of {total}, leg {legs}, {failures} failures",
  runStatusPausedTemplate: "Paused — {completed}/{total} complete, {failures} failures",
  runStatusOutcomeTemplate: "{outcome} — {completed}/{total} complete, {failures} failures",
  // Sentinel-event surface — surfaces the parsed sentinels per
  // behavior/checklists.md §"Sentinels".
  sentinelEventAriaLabel: "Item state",
  sentinelEventTooltipNone: "Not yet attempted by a driver, no paired chat.",
  sentinelEventTooltipSlate: "Has a paired chat, no run currently driving the item.",
  sentinelEventTooltipBlue: "The autonomous driver currently has this item active.",
  sentinelEventTooltipGreen: "Item is checked.",
  sentinelEventTooltipAmber: "Item is blocked.",
  sentinelEventTooltipRed: "Item failed.",
  sentinelEventTooltipGrey: "Item was skipped.",
  // ChecklistChat surface — the embedded conversation pane.
  checklistChatAriaLabel: "Paired chat",
  checklistChatNoSelection: "Select a checklist item with a paired chat to continue.",
  checklistChatBreadcrumbPrefix: "Working on",
  checklistChatSentinelHeading: "Sentinel events",
  checklistChatSentinelEmpty: "No sentinels in the latest assistant turn.",
  // Per-sentinel-kind label (sentinel kind → user-visible chip).
  sentinelKindLabels: {
    item_done: "item done",
    handoff: "handoff",
    followup_blocking: "followup (blocking)",
    followup_nonblocking: "followup (non-blocking)",
    item_blocked: "item blocked",
    item_failed: "item failed",
  } as const satisfies Record<string, string>,
  // Failure-on-item template (mirrors backend
  // ``DRIVER_OUTCOME_HALTED_FAILURE_TEMPLATE``).
  driverOutcomeHaltedFailureTemplate: "Halted: failure on item {itemId}",
} as const;

// ---- Derivations -----------------------------------------------------------

/**
 * Split a slash-namespaced tag name into ``[group, leaf]``.
 *
 * - ``"bearings/architect"`` → ``["bearings", "architect"]``;
 * - ``"general"`` → ``[null, "general"]`` (default/ungrouped bucket);
 * - ``"/leading-slash"`` → ``[null, "/leading-slash"]`` (the empty
 *   prefix is treated as ungrouped, matching the backend's
 *   ``Tag.group`` property which returns ``None`` when the separator
 *   appears at index 0 or not at all).
 */
export function splitTagName(name: string): readonly [string | null, string] {
  const sepIndex = name.indexOf(TAG_GROUP_SEPARATOR);
  if (sepIndex <= 0) {
    return [null, name];
  }
  return [name.slice(0, sepIndex), name.slice(sepIndex + 1)];
}
