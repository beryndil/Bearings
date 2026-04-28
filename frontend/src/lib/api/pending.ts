/**
 * Pending-operations API client (Phase 16 of docs/context-menu-plan.md).
 *
 * Thin wrapper over `/api/pending` (see src/bearings/api/routes_pending.py).
 * Every call takes an absolute project directory because pending ops
 * are per-project, not per-session — a single Bearings instance can
 * serve multiple checked-out trees.
 *
 * Server returns the row shape directly via the Pydantic
 * `PendingOperation` schema; we mirror it as a plain TS type rather
 * than re-deriving so the frontend can read fields without an extra
 * wrapper class. `started` arrives as an ISO-8601 string from the
 * Pydantic JSON serializer.
 */

import { jsonFetch, voidFetch } from './core';

export type PendingOperation = {
  name: string;
  description: string;
  command: string | null;
  owner: string | null;
  /** ISO-8601 UTC timestamp. */
  started: string;
};

export function listPending(
  directory: string,
  fetchImpl: typeof fetch = fetch
): Promise<PendingOperation[]> {
  const params = new URLSearchParams({ directory });
  return jsonFetch<PendingOperation[]>(fetchImpl, `/api/pending?${params}`);
}

/** Mark one op resolved. Returns the resolved row so a caller can
 * surface "resolved <name>" without a refetch. 404 when the name is
 * unknown — the server distinguishes "you tried to resolve a stale
 * id" from idempotent retries (CLI primitive returns None silently). */
export function resolvePending(
  directory: string,
  name: string,
  fetchImpl: typeof fetch = fetch
): Promise<PendingOperation> {
  const params = new URLSearchParams({ directory });
  return jsonFetch<PendingOperation>(
    fetchImpl,
    `/api/pending/${encodeURIComponent(name)}/resolve?${params}`,
    { method: 'POST' }
  );
}

/** Alias-shape "remove this pending op" verb — same server primitive
 * as resolve, returned with no body (204). The pending store reaches
 * for this when the user clicks Dismiss; the verb is a UX-only split
 * (see actions/pending_operation.ts). */
export function deletePending(
  directory: string,
  name: string,
  fetchImpl: typeof fetch = fetch
): Promise<void> {
  const params = new URLSearchParams({ directory });
  return voidFetch(fetchImpl, `/api/pending/${encodeURIComponent(name)}?${params}`, {
    method: 'DELETE',
  });
}
