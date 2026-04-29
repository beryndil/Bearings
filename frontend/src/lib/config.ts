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
 * render the downgrade banner with the "Use anyway" override; the
 * other source values are part of the spec alphabet but not yet
 * referenced from this layer (later items consume them).
 */
export const ROUTING_SOURCE_TAG_RULE = "tag_rule";
export const ROUTING_SOURCE_QUOTA_DOWNGRADE = "quota_downgrade";

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
