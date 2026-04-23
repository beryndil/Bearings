/**
 * Checkpoint HTTP client (Phase 7 of docs/context-menu-plan.md).
 *
 * Thin wrapper over the four `/api/sessions/{id}/checkpoints` endpoints
 * backed by `src/bearings/api/routes_checkpoints.py`. Handlers in
 * `context-menu/actions/` call these directly; the `CheckpointsStore`
 * in `$lib/stores/checkpoints.svelte` layers a reactive cache on top
 * for the gutter UI.
 *
 * Shape note: `CheckpointForkRequest.title` maps straight to the
 * server-side field — omit to inherit `"<source title> (fork)"`,
 * pass an explicit string to override.
 */

import type { Session } from './sessions';
import { jsonFetch, voidFetch } from './core';

export type Checkpoint = {
  id: string;
  session_id: string;
  /** Nullable reflects the `ON DELETE SET NULL` FK — a reorg audit
   * that drops the anchor message leaves the checkpoint row alive as
   * a session-level label with no jump target. Chip UI renders the
   * orphan state (greyed, no jump on click, fork disabled). */
  message_id: string | null;
  /** Nullable so auto-created checkpoints ("before risky prompt")
   * need no generated name. UI falls back to "Untitled" when null. */
  label: string | null;
  created_at: string;
};

export type CheckpointCreate = {
  message_id: string;
  label?: string | null;
};

export type CheckpointForkRequest = {
  /** Explicit title override. Omit to inherit `"<source> (fork)"`. */
  title?: string | null;
};

export function listCheckpoints(
  sessionId: string,
  fetchImpl: typeof fetch = fetch
): Promise<Checkpoint[]> {
  return jsonFetch<Checkpoint[]>(
    fetchImpl,
    `/api/sessions/${sessionId}/checkpoints`
  );
}

export function createCheckpoint(
  sessionId: string,
  body: CheckpointCreate,
  fetchImpl: typeof fetch = fetch
): Promise<Checkpoint> {
  return jsonFetch<Checkpoint>(
    fetchImpl,
    `/api/sessions/${sessionId}/checkpoints`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body)
    }
  );
}

export function deleteCheckpoint(
  sessionId: string,
  checkpointId: string,
  fetchImpl: typeof fetch = fetch
): Promise<void> {
  return voidFetch(
    fetchImpl,
    `/api/sessions/${sessionId}/checkpoints/${checkpointId}`,
    { method: 'DELETE' }
  );
}

export function forkCheckpoint(
  sessionId: string,
  checkpointId: string,
  body: CheckpointForkRequest = {},
  fetchImpl: typeof fetch = fetch
): Promise<Session> {
  return jsonFetch<Session>(
    fetchImpl,
    `/api/sessions/${sessionId}/checkpoints/${checkpointId}/fork`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body)
    }
  );
}
