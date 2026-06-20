/**
 * Typed client for ``GET /api/sessions``.
 *
 * Mirrors the response shape declared by
 * :class:`bearings.web.models.sessions.SessionOut`. Per arch §1.2 the
 * client is one file per backend route group, so this module owns the
 * ``sessions`` surface; ``tags.ts`` owns the ``tags`` surface, etc.
 *
 * The query shape for tag filtering is repeated ``tag_ids`` per
 * ``docs/behavior/chat.md`` §"creates a chat" + master item #537's
 * "OR semantics across tags" — a session matching ANY of the listed
 * tags is included. The backend route is
 * :func:`bearings.web.routes.sessions.list_sessions`; this client's
 * job is to project the ``Iterable<number>`` of selected tag ids onto
 * the wire shape.
 */
import {
  API_SESSIONS_ENDPOINT,
  SESSIONS_DEFAULT_PAGE_SIZE,
  sessionModelEndpoint,
  sessionStopEndpoint,
  spawnFromReplyEndpoint,
} from "../config";
import {
  ApiError,
  deleteResource,
  getJson,
  patchJson,
  postJson,
  putJson,
  type RequestOptions,
} from "./client";

/**
 * Wire shape for one session row — one-to-one with
 * :class:`bearings.web.models.sessions.SessionOut`. The fields the
 * sidebar actually reads are ``id``, ``kind``, ``title``, ``pinned``,
 * ``error_pending``, ``closed_at``, ``checklist_item_id``,
 * ``updated_at``. The remainder is round-tripped so a future
 * inspector / conversation-header consumer doesn't have to broaden
 * the type.
 */
export interface SessionOut {
  id: string;
  kind: string;
  title: string;
  description: string | null;
  session_instructions: string | null;
  working_dir: string;
  model: string;
  permission_mode: string | null;
  max_budget_usd: number | null;
  total_cost_usd: number;
  message_count: number;
  last_context_pct: number | null;
  last_context_tokens: number | null;
  last_context_max: number | null;
  pinned: boolean;
  error_pending: boolean;
  checklist_item_id: number | null;
  created_at: string;
  updated_at: string;
  last_viewed_at: string | null;
  last_completed_at: string | null;
  closed_at: string | null;
  /**
   * Agent-authored 1-3 sentence summary of why the session was
   * closed, written by the ``close_session`` MCP tool when the agent
   * judges the user's task complete. Surfaced as the sidebar tooltip
   * on closed rows; ``null`` for rows closed manually (or never).
   */
  closing_summary: string | null;
  /**
   * Paired-chat parent title (when chat is linked to a checklist item).
   * ``null`` when the chat is unpaired or the parent has been deleted.
   * Shown in the sidebar as ``↳ <parent_title>``.
   */
  paired_parent_title?: string | null;
  /** Back-pointer to the assistant message that triggered a spawn-from-reply
   *  (gap-cycle-03-007). ``null`` on every session not created via that flow. */
  pivot_message_id?: string | null;
  /** Back-pointer to the parent session for a spawn-from-reply chat.
   *  ``null`` on every session not created via that flow. */
  parent_session_id?: string | null;
  /**
   * Classification flag (T2-07 / T3-03). Set to ``true`` by
   * ``POST /api/sessions/{id}/spawn_classify`` when the session is found
   * to contain credentials or PII. Consumed by
   * :class:`SpawnClassifiedCard` to render a warning banner above the
   * conversation body. Defaults to ``false`` when the backend row
   * predates the column (via DB migration default ``0``).
   */
  classified?: boolean;
  /**
   * Tags embedded in the session list response (PERF-NET-01 batch join).
   * Populated by ``GET /api/sessions`` via a single batch JOIN; an empty
   * array for sessions with no tags. Treat an absent field as ``[]`` for
   * back-compat with any client that held a cached ``SessionOut`` from
   * before the embed landed.
   */
  tags?: SessionTagOut[];
}

/**
 * Tag shape embedded in :interface:`SessionOut` — a minimal subset of the
 * full :interface:`TagOut` from ``api/tags.ts`` used by the session list.
 * Kept as a local alias to avoid a circular import between
 * ``api/sessions.ts`` and ``api/tags.ts``; the full ``TagOut`` is still
 * used by the tags store and standalone tag endpoints.
 */
export interface SessionTagOut {
  id: number;
  name: string;
  color: string | null;
  default_model: string | null;
  working_dir: string | null;
  pinned: boolean;
  class_: string;
  sort_order: number;
  group: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Paginated response for ``GET /api/sessions`` (PERF-BUG-001 + PERF-BUG-005).
 *
 * Mirrors :class:`bearings.web.models.sessions.SessionsPage`.
 *
 * ``total`` is the count of ALL rows matching the active filters.
 * ``next_offset`` is the offset for the next page request, or ``null``
 * when all sessions have been returned.
 */
export interface SessionsPage {
  sessions: SessionOut[];
  total: number;
  next_offset: number | null;
}

interface ListSessionsParams {
  /** ``"chat"`` / ``"checklist"`` — narrows the result by ``sessions.kind``. */
  kind?: string;
  /** ``false`` excludes rows whose ``closed_at`` is set. */
  includeClosed?: boolean;
  /**
   * Legacy OR-semantics filter — sessions attached to **at least
   * one** of the listed ids appear regardless of class. Retained for
   * back-compat with v0.18.x callers; new callers should use the
   * three per-class params instead.
   */
  tagIds?: Iterable<number>;
  /**
   * Project-class faceted filter. OR within; AND with the other two
   * sections. An empty / undefined iterable means "no constraint
   * from this class" (the route omits the param).
   */
  tagIdsProject?: Iterable<number>;
  /** Severity-class faceted filter; same OR-within / AND-across shape. */
  tagIdsSeverity?: Iterable<number>;
  /** General-class (other) faceted filter; same OR-within / AND-across shape. */
  tagIdsOther?: Iterable<number>;
  /**
   * "No severity" synthetic filter (gap-cycle-18-003). When ``true``,
   * maps to ``?severity_none=true`` on the wire. Composes OR with
   * ``tagIdsSeverity`` within the severity section — sessions with no
   * severity OR sessions matching the listed severity ids are returned.
   */
  severityNone?: boolean;
  /**
   * Maximum rows per page (PERF-BUG-001 + PERF-BUG-005). Defaults to
   * :const:`SESSIONS_DEFAULT_PAGE_SIZE` when omitted; clamped to
   * :const:`SESSIONS_MAX_PAGE_SIZE` by the backend.
   */
  limit?: number;
  /**
   * Zero-based row offset for the requested page. Pass the
   * ``next_offset`` value from the previous :interface:`SessionsPage`
   * response to fetch the next page. Defaults to ``0`` (first page).
   */
  offset?: number;
  signal?: AbortSignal;
}

/**
 * Fetch the session list with the requested filters applied.
 *
 * @throws :class:`ApiError` on non-2xx responses (422 for an unknown
 *   ``kind``, 5xx for backend faults).
 */
/**
 * Stamp ``last_viewed_at`` via ``POST /api/sessions/{id}/viewed``.
 *
 * Fire after the user selects a sidebar row or after the browser tab
 * regains visibility while a session is already selected. The server
 * upserts the updated row via the sessions-broadcast WebSocket so the
 * unviewed amber dot clears on any other open tab/window within the
 * same tick. Failures are cosmetic (the dot stays amber); callers
 * should fire-and-forget.
 *
 * @throws :class:`ApiError` on 404 (session not found) or 5xx.
 */
export async function markSessionViewed(
  sessionId: string,
  options: RequestOptions = {},
): Promise<SessionOut> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/viewed`;
  return await postJson<SessionOut>(path, null, options);
}

/**
 * Reopen a closed session via ``POST /api/sessions/{id}/reopen``. The
 * server clears ``closed_at`` while preserving any ``closing_summary``
 * (per ``docs/behavior/paired-chats.md`` §"Reopen semantics" — the
 * agent-authored summary stays available as session metadata so the
 * operator can see what the agent thought it had finished). Returns
 * the refreshed session row.
 */
export async function reopenSession(
  sessionId: string,
  options: RequestOptions = {},
): Promise<SessionOut> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/reopen`;
  return await postJson<SessionOut>(path, null, options);
}

/**
 * User-driven recovery from ERROR state.
 *
 * Calls ``POST /api/sessions/{id}/recover``, which clears
 * ``error_pending`` in the DB and triggers a runner respawn so the
 * next prompt can proceed without the user sending a message first.
 *
 * Per ``docs/behavior/chat.md`` §"Error states" and
 * ``TODO.md`` §"POST /api/sessions/{id}/recover".
 */
export async function recoverSession(
  sessionId: string,
  options: RequestOptions = {},
): Promise<SessionOut> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/recover`;
  return await postJson<SessionOut>(path, null, options);
}

/**
 * Wire shape for ``POST /api/sessions`` — one-to-one with
 * :class:`bearings.web.models.sessions.SessionCreate`. ``tag_ids``
 * defaults to an empty list at the API boundary; the new-session form
 * enforces the "≥1 tag" rule at the UI layer.
 *
 * Not exported: the only consumer today is :func:`createSession`'s
 * argument list. A second consumer would re-export from here; until
 * that lands, knip flags an exported-but-unused declaration.
 */
interface SessionCreateBody {
  kind: string;
  title: string;
  working_dir: string | null;
  model: string;
  description?: string | null;
  session_instructions?: string | null;
  permission_mode?: string | null;
  max_budget_usd?: number | null;
  tag_ids?: number[];
  /** Routing-decision projection — persisted so supervisor respawns and
   *  mid-session model swaps reconstruct the full RoutingDecision without
   *  falling back to template defaults. ``null`` means "no advisor". */
  routing_advisor_model?: string | null;
  routing_advisor_max_uses?: number;
  routing_effort_level?: string;
}

/**
 * Create a session via ``POST /api/sessions``. The server returns 201
 * with the freshly-created :class:`SessionOut` row and a ``Location``
 * header pointing at ``/api/sessions/<id>``. Caller follows up with
 * :func:`sendPrompt` if it has a first-message payload (the create
 * endpoint itself only inserts the row; queueing the first user turn
 * is a separate step so the create flow can succeed even when the
 * runner-factory is offline).
 */
export async function createSession(
  body: SessionCreateBody,
  options: RequestOptions = {},
): Promise<SessionOut> {
  return await postJson<SessionOut>(API_SESSIONS_ENDPOINT, body, options);
}

/**
 * Request the runner to interrupt the current in-flight turn via
 * ``POST /api/sessions/{id}/stop``. The server returns 204 No Content;
 * this function returns ``void`` on success.
 *
 * Idempotent: safe to call when no turn is running — the server
 * no-ops and still returns 204.
 *
 * @throws :class:`ApiError` on 404 (session not found) or 5xx.
 */
export async function stopSession(sessionId: string): Promise<void> {
  const HTTP_OK_MIN = 200;
  const HTTP_OK_MAX = 300;
  const response = await fetch(sessionStopEndpoint(sessionId), {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (response.status < HTTP_OK_MIN || response.status >= HTTP_OK_MAX) {
    let errorBody: unknown = null;
    try {
      errorBody = await response.json();
    } catch {
      try {
        errorBody = await response.text();
      } catch {
        // ignore
      }
    }
    throw new ApiError(
      response.status,
      errorBody,
      `POST stop ${sessionId} → ${response.status} ${response.statusText}`,
    );
  }
  // 204 No Content — nothing to parse.
}

/**
 * Fetch one page of sessions with the requested filters applied
 * (PERF-BUG-001 + PERF-BUG-005).
 *
 * Returns a :interface:`SessionsPage` envelope containing ``sessions``,
 * ``total`` (total matching rows across all pages), and ``next_offset``
 * (``null`` when the last page has been delivered). Pass ``next_offset``
 * as ``params.offset`` to fetch the next page.
 *
 * ``tags`` on each :interface:`SessionOut` row are populated from the
 * backend's single-batch JOIN (PERF-NET-01) — no per-row tag fetches
 * are required by the caller.
 *
 * @throws :class:`ApiError` on non-2xx responses (422 for an unknown
 *   ``kind``, 5xx for backend faults).
 */
export async function listSessions(params: ListSessionsParams = {}): Promise<SessionsPage> {
  const query: Array<readonly [string, string]> = [];
  if (params.kind !== undefined) {
    query.push(["kind", params.kind]);
  }
  if (params.includeClosed !== undefined) {
    query.push(["include_closed", params.includeClosed ? "true" : "false"]);
  }
  if (params.tagIds !== undefined) {
    for (const id of params.tagIds) {
      query.push(["tag_ids", String(id)]);
    }
  }
  if (params.tagIdsProject !== undefined) {
    for (const id of params.tagIdsProject) {
      query.push(["tag_ids_project", String(id)]);
    }
  }
  if (params.tagIdsSeverity !== undefined) {
    for (const id of params.tagIdsSeverity) {
      query.push(["tag_ids_severity", String(id)]);
    }
  }
  if (params.tagIdsOther !== undefined) {
    for (const id of params.tagIdsOther) {
      query.push(["tag_ids_other", String(id)]);
    }
  }
  if (params.severityNone) {
    query.push(["severity_none", "true"]);
  }
  // Pagination params — always send limit so the wire is explicit;
  // offset is omitted when 0 (backend default) to keep URLs clean on
  // first-page loads.
  const effectiveLimit = params.limit ?? SESSIONS_DEFAULT_PAGE_SIZE;
  query.push(["limit", String(effectiveLimit)]);
  if (params.offset !== undefined && params.offset > 0) {
    query.push(["offset", String(params.offset)]);
  }
  const options: RequestOptions = {};
  if (query.length > 0) {
    options.query = query;
  }
  if (params.signal !== undefined) {
    options.signal = params.signal;
  }
  return await getJson<SessionsPage>(API_SESSIONS_ENDPOINT, options);
}

/**
 * Return the single most-recently-updated session row (open or closed),
 * or ``null`` when no sessions exist yet. Used by the new-session form
 * to pre-fill ``working_dir`` and ``model`` from the previous session
 * (item 3.4 default-from-last-session auto-fill).
 *
 * The underlying list endpoint sorts by ``updated_at DESC``, so the
 * first row is always the most recently touched session — exactly the
 * right source for "what did the user use last time?"
 */
export async function getMostRecentSession(signal?: AbortSignal): Promise<SessionOut | null> {
  const page = await listSessions({ includeClosed: true, limit: 1, signal });
  return page.sessions[0] ?? null;
}

/**
 * Swap the session's executor model via
 * ``PATCH /api/sessions/{id}/model`` (spec §7).
 *
 * The server persists the new model name and recycles the live SDK
 * supervisor.  The sessions-broadcast WS will upsert the returned row
 * into the sessions store automatically.
 *
 * @throws :class:`ApiError` on 404 (session not found), 422 (unknown model
 *   name), or 5xx.
 */
export async function patchSessionModel(
  sessionId: string,
  model: string,
  options: RequestOptions = {},
): Promise<SessionOut> {
  const path = sessionModelEndpoint(sessionId);
  return await patchJson<SessionOut>(path, { model }, options);
}

/**
 * Swap the session's permission mode via
 * ``PATCH /api/sessions/{id}/permission_mode`` (item 3.3).
 *
 * ``null`` clears the column — the runner uses the profile default on the
 * next boot. The server returns the full updated :class:`SessionOut` row.
 *
 * @throws :class:`ApiError` on 404 (session not found), 422 (unknown mode),
 *   or 5xx.
 */
export async function patchSessionPermissionMode(
  sessionId: string,
  permissionMode: string | null,
  options: RequestOptions = {},
): Promise<SessionOut> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/permission_mode`;
  return await patchJson<SessionOut>(path, { permission_mode: permissionMode }, options);
}

/**
 * Regenerate from the last message via ``POST /api/sessions/{id}/regenerate``.
 * Inserts a re-roll boundary (per ``docs/behavior/chat.md`` §"What a message turn looks like").
 * The server queues a synthetic prompt and the runner will re-generate from the
 * last message. Returns 204 No Content on success.
 *
 * @throws :class:`ApiError` on 404 (session not found) or 5xx.
 */
export async function regenerateSession(
  sessionId: string,
  options: RequestOptions = {},
): Promise<void> {
  const HTTP_OK_MIN = 200;
  const HTTP_OK_MAX = 300;
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/regenerate`;
  const response = await fetch(path, {
    method: "POST",
    headers: { Accept: "application/json" },
    signal: options.signal,
  });
  if (response.status < HTTP_OK_MIN || response.status >= HTTP_OK_MAX) {
    let errorBody: unknown = null;
    try {
      errorBody = await response.json();
    } catch {
      try {
        errorBody = await response.text();
      } catch {
        // ignore
      }
    }
    throw new ApiError(
      response.status,
      errorBody,
      `POST regenerate ${sessionId} → ${response.status} ${response.statusText}`,
    );
  }
  // 204 No Content — nothing to parse.
}

/**
 * Truncate the conversation to the pivot user message preceding
 * ``messageId`` and re-queue that user message via
 * ``POST /api/sessions/{id}/regenerate_from/{messageId}``.
 *
 * ``messageId`` must name an assistant-role turn. The server deletes all
 * messages after the preceding user message (including the clicked
 * assistant turn) and re-dispatches that user message to the runner.
 *
 * @throws :class:`ApiError` on 404 (session/message not found or no
 *   preceding user message), 409 (session closed), 422 (not an assistant
 *   turn), 429 (rate limited), or 5xx.
 *
 * Per ``docs/behavior/chat.md`` §"Regenerate from here" (gap-cycle-03-006).
 */
export async function regenerateFromMessage(
  sessionId: string,
  messageId: string,
  options: RequestOptions = {},
): Promise<void> {
  const HTTP_OK_MIN = 200;
  const HTTP_OK_MAX = 300;
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/regenerate_from/${encodeURIComponent(messageId)}`;
  const response = await fetch(path, {
    method: "POST",
    headers: { Accept: "application/json" },
    signal: options.signal,
  });
  if (response.status < HTTP_OK_MIN || response.status >= HTTP_OK_MAX) {
    let errorBody: unknown = null;
    try {
      errorBody = await response.json();
    } catch {
      try {
        errorBody = await response.text();
      } catch {
        // ignore
      }
    }
    throw new ApiError(
      response.status,
      errorBody,
      `POST regenerate_from ${sessionId}/${messageId} → ${response.status} ${response.statusText}`,
    );
  }
}

/**
 * Fetch paired-chat metadata for a chat session.
 *
 * Returns ``{parent_title, item_label}`` when paired to a checklist item,
 * or ``null`` when unpaired. The breadcrumb chip on the conversation header
 * uses this to render ``<parent checklist title> › <item label>``.
 */
export interface PairedChatInfo {
  parent_title: string;
  item_label: string;
}

export async function getPairedChatInfo(
  sessionId: string,
  options: RequestOptions = {},
): Promise<PairedChatInfo | null> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/paired-chat-info`;
  return await getJson<PairedChatInfo | null>(path, options);
}

/**
 * Archive (close) a session via ``POST /api/sessions/{id}/close``.
 * Stamps ``closed_at`` to now, moving the row to the sidebar's closed group.
 */
export async function closeSession(
  sessionId: string,
  options: RequestOptions = {},
): Promise<SessionOut> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/close`;
  return await postJson<SessionOut>(path, null, options);
}

/**
 * Delete a session permanently via ``DELETE /api/sessions/{id}``.
 * Cascades to messages, checkpoints, and session_tags rows.
 */
export async function deleteSession(
  sessionId: string,
  options: RequestOptions = {},
): Promise<void> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}`;
  return await deleteResource<void>(path, options);
}

/**
 * Pin or unpin a session via ``PATCH /api/sessions/{id}/pinned``.
 * ``pinned=true`` pins the row; ``pinned=false`` unpins it.
 */
export async function patchSessionPinned(
  sessionId: string,
  pinned: boolean,
  options: RequestOptions = {},
): Promise<SessionOut> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/pinned`;
  return await patchJson<SessionOut>(path, { pinned }, options);
}

/**
 * Duplicate a session via ``POST /api/sessions``, cloning the title,
 * session_instructions, working_dir, and model from the source row.
 * Message history is NOT copied — only the session metadata.
 */
export async function duplicateSession(
  source: SessionOut,
  options: RequestOptions = {},
): Promise<SessionOut> {
  const body = {
    kind: source.kind,
    title: `${source.title} (copy)`,
    working_dir: source.working_dir,
    model: source.model,
    session_instructions: source.session_instructions ?? null,
    permission_mode: source.permission_mode ?? null,
    tag_ids: [] as number[],
  };
  return await postJson<SessionOut>(API_SESSIONS_ENDPOINT, body, options);
}

/**
 * Trigger a browser download of the session's full JSON export.
 *
 * Calls ``GET /api/sessions/{id}/export``, converts the response to a
 * ``Blob``, and triggers an ``<a download>`` click so the browser saves
 * the file. The download filename is derived from the session title:
 * non-alphanumeric runs are collapsed to ``-``, the result is
 * lowercased, and ``".json"`` is appended. Falls back to ``session.json``
 * when the slug is empty (title contained only special characters).
 *
 * Per ``docs/behavior/sessions.md`` §"Export contract" — any session
 * (including closed ones) is exportable.
 *
 * @throws :class:`ApiError` on non-2xx responses (404 when the session
 *   is missing).
 */
export async function exportSessionJson(
  session: SessionOut,
  options: RequestOptions = {},
): Promise<void> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(session.id)}/export`;
  const resp = await fetch(path, {
    method: "GET",
    signal: options.signal,
  });
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new ApiError(resp.status, body, `GET ${path} → ${resp.status} ${resp.statusText}`);
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const slug =
    session.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "session";
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${slug}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

/**
 * Update the title of a session via ``PATCH /api/sessions/{id}``.
 */
export async function patchSessionTitle(
  sessionId: string,
  title: string,
  options: RequestOptions = {},
): Promise<SessionOut> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}`;
  return await patchJson<SessionOut>(path, { title }, options);
}

/**
 * Wire shape for the full ``PATCH /api/sessions/{id}`` surface.
 *
 * All fields are optional; only supplied fields are written (true PATCH
 * semantics). ``null`` clears a nullable column.  ``tag_ids`` replaces
 * the session's tag set wholesale when present.
 *
 * Gap: gap-cycle-10-001 (SessionEdit modal).
 */
interface SessionPatchBody {
  title?: string;
  description?: string | null;
  max_budget_usd?: number | null;
  session_instructions?: string | null;
  tag_ids?: number[];
}

/**
 * Apply a partial update to a session via ``PATCH /api/sessions/{id}``.
 *
 * Any field in ``body`` overwrites the stored value; omitted fields are
 * left unchanged. To clear a nullable field send ``null`` explicitly
 * (e.g. ``{ description: null }``).
 *
 * @throws :class:`ApiError` on 404 (session not found), 422 (bad value
 *   — e.g. empty title, negative budget, unknown tag_id), or 5xx.
 */
export async function patchSession(
  sessionId: string,
  body: SessionPatchBody,
  options: RequestOptions = {},
): Promise<SessionOut> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}`;
  return await patchJson<SessionOut>(path, body, options);
}

/**
 * Import a session from an export JSON blob via
 * ``POST /api/sessions/import``.
 *
 * ``exportJson`` must be a parsed object matching the ``SessionExport``
 * wire shape (the same object you get from
 * ``GET /api/sessions/{id}/export``).  Pass ``force=true`` to overwrite
 * an existing session with the same id (default: ``false`` — returns a
 * 409 :class:`ApiError` when the session_id is already present).
 *
 * @returns The newly created :class:`SessionOut` row (HTTP 201).
 * @throws :class:`ApiError` on 409 (duplicate, force not set), 422
 *   (malformed export), or 5xx.
 *
 * Per ``docs/behavior/sessions.md`` §"Import contract".
 */
export async function importSessionJson(
  exportJson: object,
  options: RequestOptions & { force?: boolean } = {},
): Promise<SessionOut> {
  const { force = false, ...rest } = options;
  const path = force
    ? `${API_SESSIONS_ENDPOINT}/import?force=true`
    : `${API_SESSIONS_ENDPOINT}/import`;
  return await postJson<SessionOut>(path, exportJson, rest);
}

/**
 * Spawn-from-reply response shape — mirrors
 * :class:`bearings.web.models.spawn_from_reply.SpawnFromReplyOut`.
 *
 * ``created`` is ``true`` on first spawn (HTTP 201) and ``false``
 * when the idempotent path returned an existing open session (HTTP 200).
 */
interface SpawnFromReplyOut {
  chat_session_id: string;
  parent_session_id: string;
  pivot_message_id: string;
  title: string;
  working_dir: string;
  model: string;
  created: boolean;
}

/**
 * Spawn a paired chat seeded with a blockquote of the given assistant message.
 *
 * Backed by ``POST /api/sessions/{parentId}/spawn_from_reply/{messageId}``
 * (gap-cycle-03-007). The call is idempotent: a second call for the same
 * ``messageId`` returns the already-spawned open session (HTTP 200,
 * ``created: false``) instead of creating a duplicate.
 *
 * @throws :class:`ApiError` on 404 (unknown parent / message), 422
 *   (non-assistant pivot message), or 5xx.
 */
export async function spawnFromReply(
  parentSessionId: string,
  messageId: string,
  options: RequestOptions = {},
): Promise<SpawnFromReplyOut> {
  return await postJson<SpawnFromReplyOut>(
    spawnFromReplyEndpoint(parentSessionId, messageId),
    {},
    options,
  );
}

/**
 * Wire shape for ``GET /api/sessions/{id}/tokens`` (gap-cycle-13-003).
 *
 * Aggregated lifetime token totals from persisted ``message_complete``
 * rows.  All fields are non-negative integers; NULLs in the DB are
 * treated as 0.  ``cache_creation`` is always ``0`` in v18 — reserved
 * for when the backend surface for ``cache_creation_tokens`` lands.
 */
export interface SessionTokenTotalsOut {
  input: number;
  output: number;
  cache_read: number;
  cache_creation: number;
}

/**
 * Fetch aggregated lifetime token totals for a session via
 * ``GET /api/sessions/{id}/tokens`` (gap-cycle-13-003).
 *
 * Called once on session open alongside ``listMessagesPage`` /
 * ``hydrateToolCalls`` / ``hydrateTodos`` so the Inspector Metrics tab
 * and the header dollar/token meter paint non-zero totals immediately
 * rather than waiting for WebSocket replay.
 *
 * Returns ``{input:0, output:0, cache_read:0, cache_creation:0}`` when
 * the session exists but has no assistant turns yet.
 *
 * @throws :class:`ApiError` on 404 (session not found) or 5xx.
 */
export async function getSessionTokens(
  sessionId: string,
  options: RequestOptions = {},
): Promise<SessionTokenTotalsOut> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/tokens`;
  return await getJson<SessionTokenTotalsOut>(path, options);
}

/**
 * Wire shape for ``GET /api/sessions/{id}/todos`` (gap-cycle-03-013).
 *
 * ``todos_json`` is the serialised ``todos`` array from the most-recent
 * ``TodoWrite`` call's input — identical in shape to the ``todos_json``
 * field on the ``todo_write_update`` WebSocket event.
 */
interface SessionTodosOut {
  todos_json: string;
}

/**
 * Fetch the most-recent persisted ``TodoWrite`` payload for a session.
 *
 * Used by the conversation pane to seed ``LiveTodos`` on session open
 * before any WebSocket event arrives.  Returns ``null`` when the session
 * has never emitted a ``TodoWrite`` call.
 *
 * Per ``docs/behavior/chat.md`` §"LiveTodos hydration contract"
 * (gap-cycle-03-013).
 *
 * @throws :class:`ApiError` on 404 (session not found) or 5xx.
 */
export async function getSessionTodos(
  sessionId: string,
  options: RequestOptions = {},
): Promise<SessionTodosOut | null> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/todos`;
  return await getJson<SessionTodosOut | null>(path, options);
}

// ---- system-prompt layer breakdown (gap-cycle-13-004) --------------------

/**
 * Wire shape for one layer of the assembled system prompt.
 *
 * Per ``docs/behavior/chat.md`` §"System-prompt layers contract".
 * Mirrors :class:`bearings.web.models.sessions.SystemPromptLayerOut`.
 */
export interface SystemPromptLayer {
  /** Layer kind — one of the LAYER_KIND_* values. */
  kind:
    | "baseline"
    | "project_claude_md"
    | "user_claude_md"
    | "user_rules_md"
    | "tag_claude_md"
    | "tag_memory"
    | "session_instructions"
    | "template_baseline";
  /** Text body of the layer. Non-empty for every returned layer. */
  body: string;
  /** Approximate token count (len(body) // 4). */
  token_count: number;
  /**
   * Absolute filesystem path for filesystem-sourced layers
   * (``project_claude_md``, ``user_claude_md``, ``user_rules_md``,
   * ``tag_claude_md``); ``null`` for DB-resident layers.
   */
  source_path: string | null;
}

/**
 * Wire shape for ``GET /api/sessions/{id}/system_prompt``.
 *
 * Per ``docs/behavior/chat.md`` §"System-prompt layers contract".
 * Mirrors :class:`bearings.web.models.sessions.SystemPromptLayersOut`.
 */
export interface SystemPromptLayersOut {
  /** Ordered layers in splice order. Absent kinds are omitted (frontend shows empty-state per section). */
  layers: SystemPromptLayer[];
  /** Sum of all layer token_count values. */
  total_tokens: number;
  /** Always true — token counts are len(body) // 4 approximations. */
  token_count_approximate: boolean;
}

/**
 * Fetch the assembled system-prompt layer breakdown for a session.
 *
 * Called by ``InspectorInstructions`` on session selection to render
 * the full set of layers the agent sees.
 *
 * Per ``docs/behavior/chat.md`` §"System-prompt layers contract"
 * (gap-cycle-13-004).
 *
 * @throws :class:`ApiError` on 404 (session not found) or 5xx.
 */
export async function getSessionSystemPrompt(
  sessionId: string,
  options: RequestOptions = {},
): Promise<SystemPromptLayersOut> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/system_prompt`;
  return await getJson<SystemPromptLayersOut>(path, options);
}

// ---- layer content write --------------------------------------------------

/**
 * Wire shape for ``PUT /api/sessions/{id}/system_prompt/layer`` response.
 *
 * Mirrors :class:`bearings.web.models.sessions.SystemPromptLayerWriteOut`.
 */
interface SystemPromptLayerWriteOut {
  path: string;
  content: string;
}

/**
 * Overwrite a filesystem-sourced system-prompt layer file.
 *
 * ``path`` must match a ``source_path`` present in the session's current
 * assembled layers — the backend validates this to prevent arbitrary writes.
 * Only ``project_claude_md`` / ``tag_claude_md`` layers carry a
 * ``source_path`` and can be written.
 *
 * @throws :class:`ApiError` on 404 (session not found or path not a layer)
 *         or 500 (OS-level write failure).
 */
export async function putSessionLayerContent(
  sessionId: string,
  path: string,
  content: string,
  options: RequestOptions = {},
): Promise<SystemPromptLayerWriteOut> {
  const endpoint = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/system_prompt/layer`;
  return await putJson<SystemPromptLayerWriteOut>(endpoint, { path, content }, options);
}

// ---- preview_title (T1-03) ------------------------------------------------

/**
 * Wire shape for ``POST /api/sessions/{id}/preview_title`` (T1-03).
 *
 * ``suggested_title`` is ``null`` when the session has no messages, the
 * underlying LLM call fails, or the response is blank.
 *
 * Not exported: the only consumer today is :func:`previewSessionTitle`'s
 * return type. A second consumer (e.g. a caller that stores the result by
 * type) would re-export from here; until that lands, knip flags an
 * exported-but-unused declaration.
 */
interface SuggestTitleOut {
  suggested_title: string | null;
}

/**
 * Request a title preview for a session via
 * ``POST /api/sessions/{id}/preview_title`` (T1-03).
 *
 * The server fetches recent messages, sends a short excerpt to the Claude
 * CLI, and returns a proposed 3-8 word title.  The caller should
 * pre-fill the ``SessionEdit`` modal's title input on success, silently
 * ignore a ``null`` result, and show a toast on network/HTTP errors.
 *
 * @throws :class:`ApiError` on 404 (session not found) or 5xx.
 */
export async function previewSessionTitle(
  sessionId: string,
  options: RequestOptions = {},
): Promise<SuggestTitleOut> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/preview_title`;
  return await postJson<SuggestTitleOut>(path, null, options);
}

// ---- work_evidence (T2-08) ------------------------------------------------

/** Per-tool-name call count within a session (spec T2-08). */
export interface WorkEvidenceToolSummary {
  tool_name: string;
  call_count: number;
}

/**
 * Work evidence summary for a session — tool-call counts + optional git
 * diff stat (spec T2-08, ``GET /api/sessions/{id}/work_evidence``).
 */
export interface WorkEvidenceOut {
  bash_calls: number;
  write_calls: number;
  edit_calls: number;
  total_work_tool_calls: number;
  git_diff_stat: string | null;
  git_diff_available: boolean;
  tool_summaries: WorkEvidenceToolSummary[];
}

/**
 * Fetch work evidence (bash/write/edit call counts + git diff stat) for
 * the given session.
 *
 * @throws :class:`ApiError` on 404 (session not found) or 5xx.
 */
export async function getWorkEvidence(
  sessionId: string,
  options: RequestOptions = {},
): Promise<WorkEvidenceOut> {
  const path = `${API_SESSIONS_ENDPOINT}/${encodeURIComponent(sessionId)}/work_evidence`;
  return await getJson<WorkEvidenceOut>(path, options);
}
