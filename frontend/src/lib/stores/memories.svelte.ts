/**
 * Memories store — per-tag CRUD over user-authored system-prompt
 * fragments (item 2.10; ``docs/architecture-v1.md`` §1.1.3).
 *
 * Memories are different from the read-only vault: they ARE editable,
 * scoped per tag. The store exposes the active tag id + the in-memory
 * list of memories for that tag plus imperative create / update /
 * delete helpers. The list is the authoritative shape — every write
 * helper refetches afterwards so optimistic-update drift cannot
 * accumulate across edits.
 */
import {
  createMemory,
  deleteMemory,
  listTagMemories,
  updateMemory,
  type TagMemoryIn,
  type TagMemoryOut,
} from "../api/memories";

interface MemoriesState {
  /** Current scope tag id, or ``null`` for "no tag selected". */
  tagId: number | null;
  /** Memories for ``tagId`` — sort order matches the API response. */
  memories: TagMemoryOut[];
  /** ``true`` while a refresh / create / update / delete is in flight. */
  loading: boolean;
  /** Last error from the most recent attempt; cleared on success. */
  error: Error | null;
}

const state: MemoriesState = $state({
  tagId: null,
  memories: [],
  loading: false,
  error: null,
});

export const memoriesStore = state;

let refreshController: AbortController | null = null;

/**
 * Refresh the per-tag memories list. Cancels any in-flight refresh so
 * a rapid second call wins. The :func:`setActiveTag` helper schedules
 * a refresh on tag change; callers also use this directly after a
 * write to repaint without waiting for a poll.
 */
export async function refreshMemories(tagId: number): Promise<void> {
  refreshController?.abort();
  const controller = new AbortController();
  refreshController = controller;
  state.loading = true;
  try {
    const memories = await listTagMemories(tagId, { signal: controller.signal });
    if (controller.signal.aborted) return;
    if (state.tagId !== tagId) {
      // Stale tag — caller switched scope mid-flight; drop.
      return;
    }
    state.memories = memories;
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
 * Switch the active tag. ``null`` clears the scope (the editor
 * renders its "pick a tag" empty state). Idempotent on the same id.
 */
export function setActiveTag(tagId: number | null): void {
  if (state.tagId === tagId) return;
  refreshController?.abort();
  refreshController = null;
  state.tagId = tagId;
  state.memories = [];
  state.error = null;
  if (tagId !== null) {
    void refreshMemories(tagId);
  }
}

/**
 * Create a memory under the active tag and refetch. Throws on the
 * underlying API error so the caller's form path can branch on
 * 422 (server-side validation) — the memories editor already
 * enforces the same caps client-side, so 422 is unreachable through
 * the form path but a stale tag id (404) is still possible.
 */
export async function createMemoryFor(tagId: number, body: TagMemoryIn): Promise<TagMemoryOut> {
  state.loading = true;
  try {
    const created = await createMemory(tagId, body);
    if (state.tagId === tagId) {
      await refreshMemories(tagId);
    }
    return created;
  } catch (error) {
    state.error = error instanceof Error ? error : new Error(String(error));
    throw error;
  } finally {
    state.loading = false;
  }
}

/** Update one memory + refetch the active list. */
export async function updateMemoryFor(memoryId: number, body: TagMemoryIn): Promise<TagMemoryOut> {
  state.loading = true;
  try {
    const updated = await updateMemory(memoryId, body);
    if (state.tagId !== null) {
      await refreshMemories(state.tagId);
    }
    return updated;
  } catch (error) {
    state.error = error instanceof Error ? error : new Error(String(error));
    throw error;
  } finally {
    state.loading = false;
  }
}

/** Delete one memory + refetch the active list. */
export async function deleteMemoryFor(memoryId: number): Promise<void> {
  state.loading = true;
  try {
    await deleteMemory(memoryId);
    if (state.tagId !== null) {
      await refreshMemories(state.tagId);
    }
  } catch (error) {
    state.error = error instanceof Error ? error : new Error(String(error));
    throw error;
  } finally {
    state.loading = false;
  }
}

/** Test seam — restores the boot state without re-importing the module. */
export function _resetForTests(): void {
  refreshController?.abort();
  refreshController = null;
  state.tagId = null;
  state.memories = [];
  state.loading = false;
  state.error = null;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
