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
import { listSessions, type SessionOut } from "../api/sessions";
import { listSessionTags, type TagOut } from "../api/tags";

interface SessionsState {
  /** Last successful list response. */
  sessions: SessionOut[];
  /** Per-session tag list — keyed by ``SessionOut.id``. */
  tagsBySessionId: Record<string, TagOut[]>;
  /** ``true`` while a refresh is in flight. */
  loading: boolean;
  /** Last error from a refresh attempt (cleared on success). */
  error: Error | null;
}

const state: SessionsState = $state({
  sessions: [],
  tagsBySessionId: {},
  loading: false,
  error: null,
});

export const sessionsStore = state;

let refreshController: AbortController | null = null;

/**
 * Refresh the sidebar list. ``tagFilter`` is the OR-semantics filter
 * set from :data:`tagsStore.selectedIds`; an empty set means "no
 * filter applied" (the route omits the ``tag_ids`` query param
 * entirely when the iterable is empty, mirroring the backend
 * contract).
 */
export async function refreshSessions(tagFilter: ReadonlySet<number>): Promise<void> {
  refreshController?.abort();
  const controller = new AbortController();
  refreshController = controller;
  state.loading = true;
  try {
    const params: Parameters<typeof listSessions>[0] = { signal: controller.signal };
    if (tagFilter.size > 0) {
      params.tagIds = tagFilter;
    }
    const sessions = await listSessions(params);
    if (controller.signal.aborted) {
      return;
    }
    state.sessions = sessions;
    // Per-session tag fetches run in parallel; one fetch per row is
    // acceptable for v1 (the typical project has ≤ a few dozen open
    // sessions). Item 2.5+ may collapse this into a single
    // ``/api/sessions?include_tags=true`` extension if the latency
    // becomes visible.
    const tagLists: Array<[string, TagOut[]]> = await Promise.all(
      sessions.map(async (session): Promise<[string, TagOut[]]> => {
        try {
          const tags = await listSessionTags(session.id, { signal: controller.signal });
          return [session.id, tags];
        } catch (error) {
          if (controller.signal.aborted || isAbortError(error)) {
            return [session.id, []];
          }
          // A single per-session fetch failure shouldn't blank the
          // whole sidebar — fall back to "no chips" for that row.
          return [session.id, []];
        }
      }),
    );
    if (controller.signal.aborted) {
      return;
    }
    const nextTagMap: Record<string, TagOut[]> = {};
    for (const [id, tags] of tagLists) {
      nextTagMap[id] = tags;
    }
    state.tagsBySessionId = nextTagMap;
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

export function _resetForTests(): void {
  state.sessions = [];
  state.tagsBySessionId = {};
  state.loading = false;
  state.error = null;
  refreshController?.abort();
  refreshController = null;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
