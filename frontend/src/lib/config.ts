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
