/**
 * Tag store — global tag list + the active sidebar filter set.
 *
 * Per arch §2.2 the canonical store for tags is a single Svelte 5
 * runes module exporting a ``$state`` proxy plus a small imperative
 * API. Two responsibilities live here:
 *
 * 1. Cache the tag list so the sidebar's filter panel + each session
 *    row's tag chips render against the same source of truth.
 * 2. Own the **active filter set** — the set of selected tag ids
 *    that the sidebar restricts visible sessions to. The set
 *    materialises OR semantics: a session matches when it carries
 *    **any** of the selected tags. Adding more tags WIDENS the
 *    visible session set; removing tags narrows it (all the way to
 *    "no filter" when the set empties out).
 *
 * Per ``docs/behavior/chat.md`` and master item #537's done-when, the
 * sidebar's tag-chip clicks call :func:`toggleTag` to flip a tag in
 * or out of the filter set. The :mod:`stores/sessions.svelte.ts`
 * store reads :data:`tagFilter.selectedIds` and refetches when it
 * changes (the components wire the reactive subscription; the stores
 * don't reach into each other).
 */
import { listTags, type TagOut } from "../api/tags";

interface TagsState {
  /** Last successful response from ``GET /api/tags``. */
  all: TagOut[];
  /** The active filter set — selected tag ids the sidebar narrows by. */
  selectedIds: ReadonlySet<number>;
  /** ``true`` while a refresh is in flight. */
  loading: boolean;
  /** Last error from a refresh attempt (cleared on success). */
  error: Error | null;
}

const state: TagsState = $state({
  all: [],
  selectedIds: new Set<number>(),
  loading: false,
  error: null,
});

/**
 * The reactive ``$state`` proxy. Components destructure from it via
 * Svelte's ``$derived`` rather than reaching into another store
 * directly (per arch §2.2's invariant).
 */
export const tagsStore = state;

/**
 * Refresh the global tag list from ``GET /api/tags``.
 *
 * The store is single-tenant — calling :func:`refresh` while a
 * previous request is in flight cancels the older one via the
 * tracked ``AbortController``.
 */
let refreshController: AbortController | null = null;

export async function refreshTags(): Promise<void> {
  refreshController?.abort();
  const controller = new AbortController();
  refreshController = controller;
  state.loading = true;
  try {
    const tags = await listTags({ signal: controller.signal });
    if (controller.signal.aborted) {
      return;
    }
    state.all = tags;
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
 * Flip ``tagId`` in or out of the filter set.
 *
 * Replaces the set wholesale (rather than mutating in place) so any
 * component bound to ``selectedIds`` via Svelte 5's reactivity sees a
 * fresh reference and re-renders. ``ReadonlySet`` on the field type
 * makes external mutation a type error.
 */
export function toggleTag(tagId: number): void {
  const next = new Set(state.selectedIds);
  if (next.has(tagId)) {
    next.delete(tagId);
  } else {
    next.add(tagId);
  }
  state.selectedIds = next;
}

/**
 * Clear the filter set (sidebar's "Clear filter" button + the user's
 * Esc-while-filter-focused path per ``keyboard-shortcuts.md`` §"Esc
 * cascade" once that wiring lands in item 2.9).
 */
export function clearTagFilter(): void {
  if (state.selectedIds.size === 0) {
    return;
  }
  state.selectedIds = new Set<number>();
}

/**
 * Reset the store to its initial values. Test-only — production code
 * never tears the store down (the page reload does that). Exported as
 * a named function so unit tests can call it explicitly rather than
 * mutating state through a backdoor.
 */
export function _resetForTests(): void {
  state.all = [];
  state.selectedIds = new Set<number>();
  state.loading = false;
  state.error = null;
  refreshController?.abort();
  refreshController = null;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
