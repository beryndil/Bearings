/**
 * Session bulk-op HTTP client (Phase 9a of docs/context-menu-plan.md).
 *
 * Thin wrapper over `POST /api/sessions/bulk`. One endpoint, five ops
 * — the response shape discriminates on `op`: mutate ops return
 * `SessionBulkResult` (`{op, succeeded, failed}`); `export` returns
 * `SessionExportBundle` (`{op, sessions, failed}`). Callers that care
 * about the distinction should branch on `body.op` before calling.
 *
 * `Session` and `Message` types intentionally aren't re-exported here
 * — the per-id export bundle is loose JSON so downstream code can
 * re-import it through `POST /api/sessions/import` without hooking
 * up a strict schema. The frontend consumes `failed` for partial-
 * failure UX; successful ids come straight off `succeeded`.
 */

import { jsonFetch } from './core';

export type SessionBulkOp = 'tag' | 'untag' | 'close' | 'delete' | 'export';

export type SessionBulkBody = {
  op: SessionBulkOp;
  ids: string[];
  payload?: { tag_id?: number } & Record<string, unknown>;
};

export type BulkFailure = { id: string; error: string };

export type SessionBulkResult = {
  op: SessionBulkOp;
  succeeded: string[];
  failed: BulkFailure[];
};

export type SessionExportEntry = {
  session: Record<string, unknown>;
  messages: Array<Record<string, unknown>>;
  tool_calls: Array<Record<string, unknown>>;
};

export type SessionExportBundle = {
  op: 'export';
  sessions: SessionExportEntry[];
  failed: BulkFailure[];
};

export type SessionBulkResponse = SessionBulkResult | SessionExportBundle;

export function bulkSessions(
  body: SessionBulkBody,
  fetchImpl: typeof fetch = fetch
): Promise<SessionBulkResponse> {
  return jsonFetch<SessionBulkResponse>(fetchImpl, '/api/sessions/bulk', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ ...body, payload: body.payload ?? {} })
  });
}
