/**
 * Checklist store — per-active-checklist items + active run + the
 * polled liveness loop.
 *
 * Per ``docs/architecture-v1.md`` §1.2 the rebuild groups feature
 * stores under ``lib/stores/`` — one file per concern. The checklist
 * pane reads:
 *
 * - the items list (tree built from ``parent_item_id`` + ``sort_order``);
 * - the active run row (state, counters, current_item_id);
 * - the per-item paired-chat pointer (for SentinelEvent's pip color
 *   derivation).
 *
 * v1 polls :func:`getChecklistOverview` while a run is live so the
 * status line ticks per ``docs/behavior/checklists.md`` §"Run-control
 * surface". A future item adds a per-checklist driver-state WS broker;
 * the polling cadence is named in
 * :data:`CHECKLIST_OVERVIEW_POLL_INTERVAL_MS`.
 */
import {
  getChecklistOverview,
  type AutoDriverRunOut,
  type ChecklistItemOut,
} from "../api/checklists";
import {
  AUTO_DRIVER_STATE_PAUSED,
  AUTO_DRIVER_STATE_RUNNING,
  CHECKLIST_OVERVIEW_POLL_INTERVAL_MS,
} from "../config";

interface ChecklistState {
  /** Current checklist session id, or ``null`` for "no checklist active". */
  checklistId: string | null;
  /** Items in `sort_order` per parent (raw — caller builds the tree). */
  items: ChecklistItemOut[];
  /** Active run row, or ``null`` if no run is in flight or recorded. */
  activeRun: AutoDriverRunOut | null;
  /** ``true`` while a refresh is in flight (initial paint only). */
  loading: boolean;
  /** Last error encountered by a refresh attempt. */
  error: Error | null;
}

const state: ChecklistState = $state({
  checklistId: null,
  items: [],
  activeRun: null,
  loading: false,
  error: null,
});

export const checklistStore = state;

let refreshController: AbortController | null = null;
let pollHandle: ReturnType<typeof setTimeout> | null = null;

/**
 * Refresh the active checklist overview (items + active run). Cancels
 * any in-flight refresh on a rapid second call.
 */
export async function refreshChecklist(checklistId: string): Promise<void> {
  refreshController?.abort();
  const controller = new AbortController();
  refreshController = controller;
  if (state.checklistId !== checklistId) {
    // Switching checklists — clear out the old data so the empty-pane
    // pass renders rather than the previous checklist's stale items.
    state.items = [];
    state.activeRun = null;
    state.checklistId = checklistId;
  }
  state.loading = state.items.length === 0;
  try {
    const overview = await getChecklistOverview(checklistId, { signal: controller.signal });
    if (controller.signal.aborted) return;
    state.items = overview.items;
    state.activeRun = overview.active_run;
    state.error = null;
  } catch (error) {
    if (controller.signal.aborted || isAbortError(error)) return;
    state.error = error instanceof Error ? error : new Error(String(error));
  } finally {
    if (refreshController === controller) {
      refreshController = null;
    }
    state.loading = false;
  }
}

/**
 * Switch the active checklist + start polling while a run is live.
 * Idempotent on the same id; clearing (``null``) stops the poll loop.
 */
export function setActiveChecklist(checklistId: string | null): void {
  if (state.checklistId === checklistId) return;
  stopPolling();
  state.checklistId = checklistId;
  state.items = [];
  state.activeRun = null;
  state.error = null;
  if (checklistId !== null) {
    void refreshChecklist(checklistId);
    schedulePoll(checklistId);
  }
}

/**
 * Force-refresh now and reschedule the poll. Component handlers call
 * this after a write (check / link / start-run / etc.) so the user
 * sees the new state without waiting for the next tick.
 */
export async function pokeChecklist(checklistId: string): Promise<void> {
  stopPolling();
  await refreshChecklist(checklistId);
  schedulePoll(checklistId);
}

function schedulePoll(checklistId: string): void {
  if (pollHandle !== null) return;
  pollHandle = setTimeout(() => {
    pollHandle = null;
    if (state.checklistId !== checklistId) return;
    // Skip the poll when no run is active or the run is terminal —
    // the user observes the items + run row only when they change,
    // and the run-row state is the cheapest gate available.
    const run = state.activeRun;
    const isLive =
      run !== null &&
      (run.state === AUTO_DRIVER_STATE_RUNNING || run.state === AUTO_DRIVER_STATE_PAUSED);
    if (isLive) {
      void refreshChecklist(checklistId).then(() => schedulePoll(checklistId));
    } else {
      // No live run — re-arm at a slow cadence so the pane still
      // reflects out-of-band edits (Tab nest, drag reorder, etc.) when
      // a future multi-tab or remote-driver path writes them.
      schedulePoll(checklistId);
    }
  }, CHECKLIST_OVERVIEW_POLL_INTERVAL_MS);
}

function stopPolling(): void {
  if (pollHandle !== null) {
    clearTimeout(pollHandle);
    pollHandle = null;
  }
  if (refreshController !== null) {
    refreshController.abort();
    refreshController = null;
  }
}

/**
 * Tree node helper — exposed so :class:`ChecklistView` can build the
 * indent tree without re-implementing the parent walk per render.
 * Returns the items grouped under each parent id, sorted by
 * ``sort_order``. Children of a missing parent are surfaced under
 * ``null`` (root) so a corrupt parent FK doesn't drop the row.
 */
export function buildChecklistTree(items: ChecklistItemOut[]): {
  roots: ChecklistItemOut[];
  childrenByParent: Map<number, ChecklistItemOut[]>;
} {
  const childrenByParent = new Map<number, ChecklistItemOut[]>();
  const roots: ChecklistItemOut[] = [];
  const known = new Set<number>(items.map((item) => item.id));
  for (const item of items) {
    if (item.parent_item_id === null || !known.has(item.parent_item_id)) {
      roots.push(item);
      continue;
    }
    const bucket = childrenByParent.get(item.parent_item_id);
    if (bucket === undefined) {
      childrenByParent.set(item.parent_item_id, [item]);
    } else {
      bucket.push(item);
    }
  }
  roots.sort((a, b) => a.sort_order - b.sort_order);
  for (const bucket of childrenByParent.values()) {
    bucket.sort((a, b) => a.sort_order - b.sort_order);
  }
  return { roots, childrenByParent };
}

export function _resetForTests(): void {
  stopPolling();
  state.checklistId = null;
  state.items = [];
  state.activeRun = null;
  state.loading = false;
  state.error = null;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
