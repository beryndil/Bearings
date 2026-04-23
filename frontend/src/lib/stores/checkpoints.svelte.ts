/**
 * Checkpoints store (Phase 7.3 of docs/context-menu-plan.md).
 *
 * Caches the checkpoint list per session. The conversation gutter reads
 * `forSession(activeSessionId)` every render; right-click action handlers
 * mutate via `create` / `remove` / `fork`. The store keeps the cache
 * reactive so the gutter re-renders as soon as the server round-trip
 * completes — no manual `refresh()` calls from component code.
 *
 * Cache shape is per-session rather than a single `current` list (the
 * pattern `checklists.svelte.ts` uses) because the sidebar chip counter
 * we'll add in a later slice needs cached checkpoint counts for sessions
 * the user isn't currently viewing. Loading stays lazy — a session with
 * no call to `load()` yields an empty array from `forSession`, not a
 * fetch-on-read side effect.
 */

import * as api from '$lib/api';
import { sessions } from '$lib/stores/sessions.svelte';

class CheckpointsStore {
  /** `sessionId -> newest-first list`. Indexed access on the Svelte 5
   * state proxy is tracked, so a gutter reading `cache[id] ?? []`
   * re-renders whenever we reassign that key. */
  private cache = $state<Record<string, api.Checkpoint[]>>({});
  /** Session currently being loaded — the gutter uses this to show a
   * subtle placeholder instead of the empty-state chip on first mount. */
  loadingFor = $state<string | null>(null);
  error = $state<string | null>(null);

  /** Reactive read. Returns an empty array for unknown sessions so the
   * gutter template stays `{#each checkpoints.forSession(id) as cp}`
   * without a null guard. */
  forSession(sessionId: string): api.Checkpoint[] {
    return this.cache[sessionId] ?? [];
  }

  /** Fetch the list for `sessionId` and replace the cached entry. Safe
   * to call repeatedly — the second call just re-fetches. */
  async load(sessionId: string): Promise<void> {
    this.loadingFor = sessionId;
    this.error = null;
    try {
      const rows = await api.listCheckpoints(sessionId);
      this.cache = { ...this.cache, [sessionId]: rows };
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
      // Leave the prior cached list in place — a failed refresh is
      // better than a blank gutter.
    } finally {
      if (this.loadingFor === sessionId) this.loadingFor = null;
    }
  }

  /** Anchor a new checkpoint at `messageId`. The server returns the
   * full row; we prepend so the gutter renders newest-first without a
   * re-fetch. Returns the created row (or null on failure) so the
   * calling action can toast feedback. */
  async create(
    sessionId: string,
    messageId: string,
    label: string | null = null
  ): Promise<api.Checkpoint | null> {
    this.error = null;
    try {
      const created = await api.createCheckpoint(sessionId, {
        message_id: messageId,
        label
      });
      const prev = this.cache[sessionId] ?? [];
      this.cache = { ...this.cache, [sessionId]: [created, ...prev] };
      return created;
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
      return null;
    }
  }

  /** Drop a checkpoint. Optimistic — removes from cache before the
   * server call so the gutter chip disappears instantly; restores on
   * failure. */
  async remove(sessionId: string, checkpointId: string): Promise<boolean> {
    const prev = this.cache[sessionId] ?? [];
    const next = prev.filter((cp) => cp.id !== checkpointId);
    if (next.length === prev.length) return false;
    this.cache = { ...this.cache, [sessionId]: next };
    try {
      await api.deleteCheckpoint(sessionId, checkpointId);
      return true;
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
      this.cache = { ...this.cache, [sessionId]: prev };
      return false;
    }
  }

  /** Fork from `checkpointId`, push the new session into the sessions
   * store so the sidebar row appears without a full refresh, and return
   * the new session. Caller decides whether to navigate via
   * `sessions.select(id)`. */
  async fork(
    sessionId: string,
    checkpointId: string,
    title: string | null = null
  ): Promise<api.Session | null> {
    this.error = null;
    try {
      const body = title === null ? {} : { title };
      const forked = await api.forkCheckpoint(sessionId, checkpointId, body);
      // Push into the sidebar list up front — the server also broadcasts
      // a `session_upsert` frame so the background poll would converge
      // anyway, but inserting now keeps the UI snappy.
      sessions.applyUpsert(forked);
      return forked;
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
      return null;
    }
  }

  /** Drop the cached entry for a session. Called by the sessions store
   * when a session is deleted (FK cascade on the server drops the rows;
   * we just mirror that locally so a future reselect doesn't flash the
   * stale list). */
  forget(sessionId: string): void {
    if (!(sessionId in this.cache)) return;
    const next = { ...this.cache };
    delete next[sessionId];
    this.cache = next;
  }

  /** Test-only: reset all state. Production callers never need this. */
  _reset(): void {
    this.cache = {};
    this.loadingFor = null;
    this.error = null;
  }
}

export const checkpoints = new CheckpointsStore();
