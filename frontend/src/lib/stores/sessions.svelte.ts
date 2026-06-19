/**
 * Sessions store — sidebar list state + per-session tag cache.
 *
 * Per arch §2.2 the canonical sidebar-list store. Owns:
 *
 * - the last ``GET /api/sessions`` snapshot (filtered by the current
 *   tag-filter selection from :mod:`stores/tags.svelte.ts`);
 * - a per-session tag map (each session's attached tags), populated
 *   alongside the list so :class:`SessionRow` can render chips
 *   without a per-row fetch storm;
 * - a single in-flight ``AbortController`` so a rapid filter toggle
 *   (or a tab refocus while the previous request is pending) cancels
 *   the older fetch.
 * - a ``/ws/sessions`` WebSocket subscription (item 2.6) that merges
 *   upserts and deletes into the local session list so all open tabs
 *   update without a full re-fetch.
 *
 * The store deliberately does NOT subscribe to the tags store —
 * components own the wiring. The pattern is:
 *
 * ```svelte
 * $effect(() => {
 *   void refreshSessions(tagsStore.selectedIds);
 * });
 * ```
 *
 * That keeps the store layer side-effect-free and makes the
 * dependency graph one-way (components depend on stores; stores never
 * depend on each other).
 */
import { untrack } from "svelte";
import { listSessions, type SessionOut } from "../api/sessions";
import type { TagOut } from "../api/tags";
import { connectSessionsBroadcast, type WorkflowRunState } from "../api/wsSessions";
import { getJson } from "../api/client";
import { API_SESSIONS_RUNNING_ENDPOINT, API_SESSIONS_AWAITING_ENDPOINT } from "../config";
import { _applyTagDelete, _applyTagUpsert } from "./tags.svelte";

interface SessionsState {
  /** Last successful list response (current page accumulation). */
  sessions: SessionOut[];
  /**
   * Per-session tag list — keyed by ``SessionOut.id``.
   *
   * Populated from the ``tags`` field embedded in each ``SessionOut``
   * row returned by ``GET /api/sessions`` (PERF-NET-01 batch join).
   * Cast to the ``TagOut`` shape from ``api/tags.ts`` for backward
   * compat with ``SessionRow`` and the tag-filter panel which were
   * written before the embed landed and already import ``TagOut``.
   */
  tagsBySessionId: Record<string, TagOut[]>;
  /** ``true`` while a refresh or load-more is in flight. */
  loading: boolean;
  /** Last error from a refresh attempt (cleared on success). */
  error: Error | null;
  /**
   * Session ids whose agent runner is currently executing a turn
   * (``is_running`` from the ``runner_state`` WS broadcast). Cleared
   * when the runner_state event sets ``is_running=false``.
   */
  running: Set<string>;
  /**
   * Session ids whose agent runner is parked waiting for the user
   * (``is_awaiting_user`` from the ``runner_state`` WS broadcast) —
   * tool-use approval or ``AskUserQuestion``. Cleared when
   * ``is_awaiting_user`` returns to false.
   */
  awaiting: Set<string>;
  /**
   * Total session rows matching the current filter (from the backend's
   * ``SessionsPage.total`` field). ``0`` on the initial empty state.
   * Used by the sidebar to determine whether a load-more affordance
   * should be shown.
   */
  total: number;
  /**
   * Offset for the next page request, or ``null`` when all sessions
   * matching the current filter have been loaded. Mirrors the backend's
   * ``SessionsPage.next_offset`` field.
   */
  nextOffset: number | null;
  /**
   * ``true`` when ``nextOffset`` is non-null, i.e. there are more
   * sessions on the server that have not yet been fetched. Derived from
   * ``nextOffset`` but stored explicitly so components can read it
   * without checking for null.
   */
  hasMore: boolean;
  /**
   * Per-session map of active background workflow runs.
   *
   * Keyed by ``WorkflowRunState.run_id``, grouped under ``session_id``.
   * A ``workflow_progress`` event with a terminal ``status`` (completed,
   * killed, error) keeps the run in the map for 8 seconds so the UI can
   * briefly show the final state before the row indicator clears.
   *
   * Components derive the ``hasBackgroundWork`` indicator from this map:
   * ``(activeWorkflows.get(sessionId) ?? []).some(r => r.status === 'running')``
   */
  activeWorkflows: Map<string, Map<string, WorkflowRunState>>;
}

const state: SessionsState = $state({
  sessions: [],
  tagsBySessionId: {},
  loading: false,
  error: null,
  running: new Set<string>(),
  awaiting: new Set<string>(),
  total: 0,
  nextOffset: null,
  hasMore: false,
  activeWorkflows: new Map<string, Map<string, WorkflowRunState>>(),
});

export const sessionsStore = state;

// ---- Sessions-broadcast WebSocket connection status -----------------------

/**
 * Reactive connection status for the sessions-broadcast WebSocket.
 *
 * Read by ``BackendStatusBanner`` to determine whether the backend is
 * reachable. Updated via the :func:`connectSessionsBroadcast` state
 * callbacks wired below.
 *
 * Initial state is ``'closed'`` — the socket is not yet open at module
 * load time. The banner's 5-second grace period means the initial closed
 * state does NOT immediately display the banner on first page load.
 */
interface WsConnectionStatus {
  /** Current logical state of the sessions-broadcast WebSocket. */
  state: "open" | "closed" | "error";
  /**
   * The close code from the most recent ``CloseEvent``, or ``null``
   * before the first close event fires. ``4401`` indicates an auth
   * failure and suppresses the backend-unreachable banner.
   */
  lastCloseCode: number | null;
}

const wsStatus: WsConnectionStatus = $state({ state: "closed", lastCloseCode: null });

/** Read-only reactive view of the sessions-broadcast WebSocket status. */
export const wsConnectionStatus: WsConnectionStatus = wsStatus;

let refreshController: AbortController | null = null;

// ---- sessions-broadcast subscription (item 2.6) ----------------------------

/**
 * Apply a ``session_upsert`` message to the local sessions list.
 *
 * If a row with the same ``id`` is already present, replace it
 * in-place so the sidebar re-renders with the new data (title
 * change, closed_at stamp, etc.). If it is new (created in another
 * tab), prepend it so it appears at the top — matching the sort order
 * the ``GET /api/sessions`` endpoint uses (newest first).
 *
 * Tag chips for the new row are NOT updated: the sidebar only shows
 * chips after the full ``refreshSessions`` cycle, and a cross-tab
 * upsert is typically a title/status change, not a tag change. A
 * later ``refreshSessions()`` call restores full tag accuracy.
 */
function _applyUpsert(session: SessionOut): void {
  const idx = state.sessions.findIndex((s) => s.id === session.id);
  if (idx >= 0) {
    state.sessions[idx] = session;
  } else {
    state.sessions = [session, ...state.sessions];
  }
}

/**
 * Apply a ``session_delete`` message by removing the matching row.
 * No-ops when the id is not in the current list.
 */
function _applyDelete(sessionId: string): void {
  state.sessions = state.sessions.filter((s) => s.id !== sessionId);
}

/**
 * Linger duration (ms) after a workflow reaches a terminal status before
 * it is evicted from ``activeWorkflows``. Gives the sidebar indicator
 * time to show the final state (killed / completed) before it clears.
 */
const _WORKFLOW_TERMINAL_LINGER_MS = 8_000;

/**
 * Apply a ``workflow_progress`` message from the sessions broadcaster.
 *
 * Inserts or updates the run entry in ``activeWorkflows`` under the
 * workflow's ``session_id`` key.  When the status is terminal
 * (``"completed" | "killed" | "error"``), schedules a removal after
 * :data:`_WORKFLOW_TERMINAL_LINGER_MS` so the indicator briefly shows
 * the final state before the session row goes back to idle.
 *
 * Map reassignment (``state.activeWorkflows = new Map(...)`` pattern)
 * is required so Svelte's proxy detects the outer Map change and
 * triggers a re-render on the session rows that read it.
 */
function _applyWorkflowProgress(run: WorkflowRunState): void {
  const { session_id, run_id, status } = run;
  const next = new Map(state.activeWorkflows);
  const sessionRuns = new Map(next.get(session_id) ?? []);
  sessionRuns.set(run_id, run);
  next.set(session_id, sessionRuns);
  state.activeWorkflows = next;

  // Schedule removal of terminal runs after a brief linger so the indicator
  // shows the completed/killed badge for a moment before clearing.
  if (status === "completed" || status === "killed" || status === "error") {
    setTimeout(() => {
      const cur = new Map(state.activeWorkflows);
      const sessionMap = cur.get(session_id);
      if (sessionMap) {
        const updated = new Map(sessionMap);
        updated.delete(run_id);
        if (updated.size === 0) {
          cur.delete(session_id);
        } else {
          cur.set(session_id, updated);
        }
        state.activeWorkflows = cur;
      }
    }, _WORKFLOW_TERMINAL_LINGER_MS);
  }
}

// ---------------------------------------------------------------------------
// REST poll fallback — running / awaiting (M-11/R-1)
// ---------------------------------------------------------------------------

/**
 * Poll ``GET /api/sessions/running`` and ``GET /api/sessions/awaiting``
 * and merge the results into the store's running/awaiting sets.
 *
 * Called on WS reconnect so runner-state indicators are restored after
 * the WebSocket was down.  Errors are silently swallowed — a failed
 * poll leaves the sets unchanged rather than crashing the sidebar.
 */
async function _pollRunningAwaiting(): Promise<void> {
  try {
    const [runningIds, awaitingIds] = await Promise.all([
      getJson<string[]>(API_SESSIONS_RUNNING_ENDPOINT),
      getJson<string[]>(API_SESSIONS_AWAITING_ENDPOINT),
    ]);
    untrack(() => {
      state.running = new Set(runningIds);
      state.awaiting = new Set(awaitingIds);
    });
  } catch {
    // Silently ignore — WS will deliver live updates once stable.
  }
}

// Start the broadcast subscription immediately when the module loads.
// ``connectSessionsBroadcast`` auto-reconnects so the subscription
// survives server restarts.  The returned ``Unsubscribe`` is not
// stored because this singleton lives for the page's lifetime.
//
// The ``options`` callbacks update ``wsStatus`` so ``BackendStatusBanner``
// can reactively reflect the connection state without a second socket.
connectSessionsBroadcast(
  (event) => {
    untrack(() => {
      if (event.type === "session_upsert") {
        _applyUpsert(event.session);
      } else if (event.type === "session_delete") {
        _applyDelete(event.session_id);
      } else if (event.type === "runner_state") {
        const { session_id, is_running, is_awaiting_user, is_error } = event;

        // Maintain running set — reassign so Svelte's proxy detects the change.
        const nextRunning = new Set(state.running);
        if (is_running) {
          nextRunning.add(session_id);
        } else {
          nextRunning.delete(session_id);
        }
        state.running = nextRunning;

        // Maintain awaiting set — same reassignment pattern.
        const nextAwaiting = new Set(state.awaiting);
        if (is_awaiting_user) {
          nextAwaiting.add(session_id);
        } else {
          nextAwaiting.delete(session_id);
        }
        state.awaiting = nextAwaiting;

        // Agent loop entered ERROR state — set error_pending locally so
        // the sidebar pip flashes without waiting for a page reload.
        // The session_upsert from the recover route will clear it.
        if (is_error) {
          const idx = state.sessions.findIndex((s) => s.id === session_id);
          if (idx !== -1) {
            state.sessions[idx] = { ...state.sessions[idx], error_pending: true };
          }
        }
      } else if (event.type === "tag_upsert") {
        // Forward tag change events to the tags store so filter panels in
        // all open tabs refresh without a full GET /api/tags round-trip
        // (feature-5-004 / CCW-3). The single /ws/sessions connection is
        // shared — no second WebSocket needed.
        _applyTagUpsert(event.tag);
      } else if (event.type === "tag_delete") {
        _applyTagDelete(event.tag_id);
      } else if (event.type === "workflow_progress") {
        _applyWorkflowProgress(event);
      }
    });
  },
  {
    onOpen() {
      untrack(() => {
        wsStatus.state = "open";
        wsStatus.lastCloseCode = null;
      });
      // REST poll fallback (M-11/R-1): restore running/awaiting sets on
      // WS reconnect in case runner_state events were missed while down.
      void _pollRunningAwaiting();
    },
    onClose(code: number) {
      untrack(() => {
        wsStatus.state = "closed";
        wsStatus.lastCloseCode = code;
      });
    },
    onError() {
      untrack(() => {
        wsStatus.state = "error";
      });
    },
  },
);

/**
 * The filter shape used by both :func:`refreshSessions` and
 * :func:`loadMoreSessions`. Exported so callers (SessionList,
 * tags.svelte's ``currentFilter``) can type the value they pass
 * without importing the shape from a different module.
 */
interface SessionFilter {
  project: ReadonlySet<number>;
  severity: ReadonlySet<number>;
  other: ReadonlySet<number>;
  severityNone?: boolean;
}

/**
 * Build the ``listSessions`` params from a :interface:`SessionFilter`.
 * Shared between :func:`refreshSessions` and :func:`loadMoreSessions`
 * so filter → params translation cannot drift between the two.
 */
function _filterToParams(filter: SessionFilter): NonNullable<Parameters<typeof listSessions>[0]> {
  const params: NonNullable<Parameters<typeof listSessions>[0]> = {};
  if (filter.project.size > 0) {
    params.tagIdsProject = filter.project;
  }
  if (filter.severity.size > 0) {
    params.tagIdsSeverity = filter.severity;
  }
  if (filter.other.size > 0) {
    params.tagIdsOther = filter.other;
  }
  if (filter.severityNone) {
    params.severityNone = true;
  }
  return params;
}

/**
 * Build ``tagsBySessionId`` from embedded tags on each ``SessionOut``
 * row (PERF-NET-01 batch join). Cast from ``SessionTagOut`` to the
 * ``TagOut`` shape the rest of the frontend uses — both are
 * structurally identical; the cast avoids adding a new import to
 * every consumer while preserving a single source of truth for the
 * wire shape.
 */
function _tagsMapFromSessions(sessions: readonly SessionOut[]): Record<string, TagOut[]> {
  const map: Record<string, TagOut[]> = {};
  for (const session of sessions) {
    // ``session.tags`` may be absent on cached/legacy rows — treat as [].
    map[session.id] = (session.tags ?? []) as unknown as TagOut[];
  }
  return map;
}

/**
 * Refresh the sidebar list using the three-section faceted tag
 * filter. Each section's set applies OR-within (a session matches
 * when it carries any of the listed tags within the class); the
 * three sections compose AND-across (a session must satisfy every
 * non-empty section). An empty section is "no constraint from this
 * class" — the route omits the matching ``tag_ids_<class>=`` query
 * param so the backend leaves it unconstrained.
 *
 * Tags are populated from the embedded ``tags`` field on each
 * :interface:`SessionOut` row (PERF-NET-01 batch join) — no
 * per-row ``GET /api/sessions/{id}/tags`` calls are issued.
 *
 * Pagination (PERF-BUG-001 + PERF-BUG-005): fetches the first page
 * (offset 0) and resets ``nextOffset`` / ``total`` / ``hasMore`` so
 * the sidebar load-more sentinel starts fresh on every filter change.
 * Call :func:`loadMoreSessions` to append subsequent pages.
 */
export async function refreshSessions(filter: SessionFilter): Promise<void> {
  refreshController?.abort();
  const controller = new AbortController();
  refreshController = controller;
  state.loading = true;
  try {
    const params = _filterToParams(filter);
    params.signal = controller.signal;
    const page = await listSessions(params);
    if (controller.signal.aborted) {
      return;
    }
    state.sessions = page.sessions;
    state.tagsBySessionId = _tagsMapFromSessions(page.sessions);
    state.total = page.total;
    state.nextOffset = page.next_offset;
    state.hasMore = page.next_offset !== null;
    state.error = null;
  } catch (error) {
    if (controller.signal.aborted || isAbortError(error)) {
      return;
    }
    state.error = error instanceof Error ? error : new Error(String(error));
  } finally {
    if (refreshController === controller) {
      refreshController = null;
    }
    state.loading = false;
  }
}

/**
 * Load the next page of sessions and append them to the current list.
 *
 * No-ops when :data:`sessionsStore.hasMore` is ``false`` or a fetch
 * is already in flight. The ``filter`` argument must match the filter
 * used in the most-recent :func:`refreshSessions` call — passing a
 * different filter would produce a mismatched append; callers should
 * always pass ``currentFilter()`` from :mod:`stores/tags.svelte`.
 *
 * On success the appended rows are merged into ``state.sessions`` and
 * the per-session tag map is extended. ``nextOffset`` / ``hasMore``
 * are updated from the page's ``next_offset`` field.
 */
export async function loadMoreSessions(filter: SessionFilter): Promise<void> {
  if (!state.hasMore || state.loading) {
    return;
  }
  const offset = state.nextOffset;
  if (offset === null) {
    return;
  }
  state.loading = true;
  try {
    const params = _filterToParams(filter);
    params.offset = offset;
    const page = await listSessions(params);
    // Merge — deduplicate by id in case a WS upsert already inserted
    // a row that the next page also returns.
    const existingIds = new Set(state.sessions.map((s) => s.id));
    const newRows = page.sessions.filter((s) => !existingIds.has(s.id));
    state.sessions = [...state.sessions, ...newRows];
    // Merge tag map — extend without replacing existing entries.
    const newTagMap = _tagsMapFromSessions(page.sessions);
    state.tagsBySessionId = { ...state.tagsBySessionId, ...newTagMap };
    state.total = page.total;
    state.nextOffset = page.next_offset;
    state.hasMore = page.next_offset !== null;
  } catch (error) {
    if (isAbortError(error)) {
      return;
    }
    // Load-more failures are non-fatal — the existing page stays; the
    // sentinel remains visible so the user can scroll to retry.
  } finally {
    state.loading = false;
  }
}

export function _resetForTests(): void {
  state.sessions = [];
  state.tagsBySessionId = {};
  state.loading = false;
  state.error = null;
  state.running = new Set<string>();
  state.awaiting = new Set<string>();
  state.total = 0;
  state.nextOffset = null;
  state.hasMore = false;
  refreshController?.abort();
  refreshController = null;
}

/** Override ``running`` ids for unit tests. */
export function _setRunningForTests(ids: string[]): void {
  state.running = new Set(ids);
}

/** Override ``awaiting`` ids for unit tests. */
export function _setAwaitingForTests(ids: string[]): void {
  state.awaiting = new Set(ids);
}

/**
 * Override ``wsConnectionStatus`` fields for unit tests.
 *
 * Directly mutates the ``$state`` object so Svelte's reactive system
 * propagates the change to any component that reads
 * ``wsConnectionStatus``.
 */
export function _setWsStatusForTests(patch: {
  state?: "open" | "closed" | "error";
  lastCloseCode?: number | null;
}): void {
  if (patch.state !== undefined) {
    wsStatus.state = patch.state;
  }
  if ("lastCloseCode" in patch) {
    wsStatus.lastCloseCode = patch.lastCloseCode ?? null;
  }
}

/** Reset ``wsConnectionStatus`` to initial state between tests. */
export function _resetWsStatusForTests(): void {
  wsStatus.state = "closed";
  wsStatus.lastCloseCode = null;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

// ---- Activity indicator (gap-cycle-08-001) ---------------------------------

/**
 * The five visible states of the per-row activity indicator pip.
 * Priority order: ``"red"`` > ``"orange"`` > ``"amber"`` > ``"green"`` > ``null``.
 *
 * ``"amber"`` is new in this release — it signals that the session has
 * one or more background workflows in flight but the agent itself is
 * between turns (idle runner). It sits below ``"orange"`` (active turn)
 * and above ``"green"`` (unviewed output) in priority so it does not
 * suppress error / active-turn signals.
 */
export type IndicatorState = "red" | "orange" | "amber" | "green" | null;

/**
 * Pure helper: resolve the activity indicator state from the five
 * boolean inputs that drive the sidebar pip.
 *
 * Priority rules (first match wins):
 * 1. ``"red"``   — agent awaiting user input OR ``error_pending`` latched.
 * 2. ``"orange"`` — agent turn is running (not parked on a question).
 * 3. ``"amber"``  — background workflow in flight (runner between turns).
 * 4. ``"green"``  — unviewed output (``last_completed_at > last_viewed_at``
 *                   and the row is not the currently-selected session).
 * 5. ``null``     — idle and caught up.
 *
 * The function is exported for direct unit-test coverage; the
 * ``SessionRow`` component derives its state by calling it with values
 * read from ``sessionsStore.running``, ``sessionsStore.awaiting``,
 * ``sessionsStore.activeWorkflows``, and the session row's own fields.
 */
export function indicatorState(params: {
  errorPending: boolean;
  awaiting: boolean;
  running: boolean;
  backgroundWork: boolean;
  unviewed: boolean;
}): IndicatorState {
  if (params.errorPending || params.awaiting) return "red";
  if (params.running) return "orange";
  if (params.backgroundWork) return "amber";
  if (params.unviewed) return "green";
  return null;
}

/**
 * Derive the ``backgroundWork`` flag for ``indicatorState`` from the
 * ``activeWorkflows`` map for a given session id.
 *
 * Returns ``true`` when the session has at least one workflow run whose
 * ``status`` is ``"running"``.  Terminal runs (completed / killed /
 * error) that are still in the map during their linger window are
 * excluded so the amber pip only shows while work is genuinely in flight.
 */
export function hasActiveWorkflows(
  activeWorkflows: Map<string, Map<string, WorkflowRunState>>,
  sessionId: string,
): boolean {
  const runs = activeWorkflows.get(sessionId);
  if (!runs || runs.size === 0) return false;
  for (const run of runs.values()) {
    if (run.status === "running") return true;
  }
  return false;
}
