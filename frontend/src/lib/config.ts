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
