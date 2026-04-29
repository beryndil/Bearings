/**
 * Typed client for ``/api/checklists/*`` and ``/api/checklist-items/*``
 * (item 1.6; ``src/bearings/web/routes/checklists.py``).
 *
 * Per ``docs/architecture-v1.md`` §1.2 each backend route group gets
 * one frontend module. The route module covers four concern groups:
 * picking / item CRUD, paired-chat linking, reorder + nesting, and
 * the auto-driver run-control surface — all four are implemented here
 * since the user observes them as one pane (``docs/behavior/
 * checklists.md`` §"What a checklist is, observably").
 *
 * Wire shapes mirror the Pydantic models in
 * :mod:`bearings.web.models.checklists`. A field rename on the backend
 * MUST be reflected here in the same commit; the route handlers use
 * ``extra="forbid"`` so a stray TS field also surfaces at the wire
 * boundary as a 422.
 */
import {
  apiChecklistEndpoint,
  apiChecklistItemEndpoint,
  apiChecklistItemsEndpoint,
  apiChecklistRunEndpoint,
} from "../config";
import { getJson, postJson, type RequestOptions } from "./client";

/**
 * Wire shape for one checklist item row — one-to-one with
 * :class:`bearings.web.models.checklists.ChecklistItemOut`.
 *
 * ``checked_at`` set ⇒ green pip; ``blocked_at`` set ⇒
 * blocked / failed / skipped pip via ``blocked_reason_category``;
 * both NULL ⇒ either "no paired chat yet" (hollow pip) or "has paired
 * chat" (slate pip) depending on ``chat_session_id`` per
 * ``docs/behavior/checklists.md`` §"Item-status colors".
 */
export interface ChecklistItemOut {
  id: number;
  checklist_id: string;
  parent_item_id: number | null;
  label: string;
  notes: string | null;
  sort_order: number;
  checked_at: string | null;
  chat_session_id: string | null;
  blocked_at: string | null;
  blocked_reason_category: string | null;
  blocked_reason_text: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Wire shape for the active-run row —  one-to-one with
 * :class:`bearings.web.models.checklists.AutoDriverRunOut`. The status
 * line in ``docs/behavior/checklists.md`` §"Run-control surface"
 * formats from these counters.
 */
export interface AutoDriverRunOut {
  id: number;
  checklist_id: string;
  state: string;
  failure_policy: string;
  visit_existing: boolean;
  items_completed: number;
  items_failed: number;
  items_blocked: number;
  items_skipped: number;
  items_attempted: number;
  legs_spawned: number;
  current_item_id: number | null;
  outcome: string | null;
  outcome_reason: string | null;
  started_at: string;
  updated_at: string;
  finished_at: string | null;
}

/**
 * Bundled overview shape — items + active-run row in one paint, per
 * :class:`bearings.web.models.checklists.ChecklistOverviewOut`.
 *
 * Not exported: the only consumer (:func:`getChecklistOverview`)
 * returns the shape and downstream callers (the checklist store) read
 * its fields off the return value without re-naming the type.
 */
interface ChecklistOverviewOut {
  checklist_id: string;
  items: ChecklistItemOut[];
  active_run: AutoDriverRunOut | null;
}

// ``PairedChatLegOut`` is not yet rendered by any UI surface in this
// item; the per-leg history view lands in a later item that adds the
// "leg history" affordance to the item row. The wire shape is kept in
// :func:`bearings.web.models.checklists.PairedChatLegOut`; this file
// re-introduces a TS mirror when the consumer arrives.

/** Bundled fetch — items + active-run in one paint. */
export async function getChecklistOverview(
  checklistId: string,
  options: RequestOptions = {},
): Promise<ChecklistOverviewOut> {
  return await getJson<ChecklistOverviewOut>(apiChecklistEndpoint(checklistId), options);
}

interface CreateItemBody {
  label: string;
  parent_item_id?: number | null;
  notes?: string | null;
}

/** Create a new checklist item. ``parent_item_id`` nests under a parent. */
export async function createChecklistItem(
  checklistId: string,
  body: CreateItemBody,
  options: RequestOptions = {},
): Promise<ChecklistItemOut> {
  return await postJson<ChecklistItemOut>(apiChecklistItemsEndpoint(checklistId), body, options);
}

interface UpdateItemBody {
  label?: string;
  notes?: string | null;
}

/** PATCH the item's label / notes. */
export async function updateChecklistItem(
  itemId: number,
  body: UpdateItemBody,
  options: RequestOptions = {},
): Promise<ChecklistItemOut> {
  return await patchJson<ChecklistItemOut>(apiChecklistItemEndpoint(itemId), body, options);
}

/** DELETE the item (cascades to children + paired_chats). */
export async function deleteChecklistItem(
  itemId: number,
  options: RequestOptions = {},
): Promise<void> {
  await sendJson("DELETE", apiChecklistItemEndpoint(itemId), null, options);
}

/** POST .../check — mark the item green. */
export async function checkChecklistItem(
  itemId: number,
  options: RequestOptions = {},
): Promise<ChecklistItemOut> {
  return await postJson<ChecklistItemOut>(`${apiChecklistItemEndpoint(itemId)}/check`, {}, options);
}

/** POST .../uncheck — clear the green pip. */
export async function uncheckChecklistItem(
  itemId: number,
  options: RequestOptions = {},
): Promise<ChecklistItemOut> {
  return await postJson<ChecklistItemOut>(
    `${apiChecklistItemEndpoint(itemId)}/uncheck`,
    {},
    options,
  );
}

// ``blockChecklistItem`` / ``unblockChecklistItem`` deliberately omitted
// — the v1 ChecklistView does not expose a manual block / unblock
// affordance (the auto-driver writes outcomes via the backend; a
// future right-click context menu adds the user-driven path). The
// route still exists; the typed client mirrors it when a consumer is
// added.

interface LinkChatBody {
  chat_session_id: string;
  spawned_by?: string;
}

/** POST .../link — set the paired-chat pointer + record a leg. */
export async function linkChecklistItemChat(
  itemId: number,
  body: LinkChatBody,
  options: RequestOptions = {},
): Promise<ChecklistItemOut> {
  return await postJson<ChecklistItemOut>(
    `${apiChecklistItemEndpoint(itemId)}/link`,
    body,
    options,
  );
}

/** POST .../unlink — clear the paired-chat pointer. */
export async function unlinkChecklistItemChat(
  itemId: number,
  options: RequestOptions = {},
): Promise<ChecklistItemOut> {
  return await postJson<ChecklistItemOut>(
    `${apiChecklistItemEndpoint(itemId)}/unlink`,
    {},
    options,
  );
}

// ``listChecklistItemLegs`` deliberately omitted — see the
// PairedChatLegOut comment above. The route exists; the consumer
// re-adds the typed mirror when a per-leg history surface lands.

interface MoveItemBody {
  parent_item_id?: number | null;
  sort_order?: number | null;
}

/** POST .../move — reparent + optionally pin sort order (drag drop). */
export async function moveChecklistItem(
  itemId: number,
  body: MoveItemBody,
  options: RequestOptions = {},
): Promise<ChecklistItemOut> {
  return await postJson<ChecklistItemOut>(
    `${apiChecklistItemEndpoint(itemId)}/move`,
    body,
    options,
  );
}

/** POST .../indent — Tab nest under previous sibling. */
export async function indentChecklistItem(
  itemId: number,
  options: RequestOptions = {},
): Promise<ChecklistItemOut> {
  return await postJson<ChecklistItemOut>(
    `${apiChecklistItemEndpoint(itemId)}/indent`,
    {},
    options,
  );
}

/** POST .../outdent — Shift+Tab pop one level out. */
export async function outdentChecklistItem(
  itemId: number,
  options: RequestOptions = {},
): Promise<ChecklistItemOut> {
  return await postJson<ChecklistItemOut>(
    `${apiChecklistItemEndpoint(itemId)}/outdent`,
    {},
    options,
  );
}

interface StartRunBody {
  failure_policy?: string;
  visit_existing?: boolean;
}

/** POST .../run/start — create a ``running`` ``auto_driver_runs`` row. */
export async function startChecklistRun(
  checklistId: string,
  body: StartRunBody,
  options: RequestOptions = {},
): Promise<AutoDriverRunOut> {
  return await postJson<AutoDriverRunOut>(
    `${apiChecklistRunEndpoint(checklistId)}/start`,
    body,
    options,
  );
}

/** POST .../run/stop — cooperative stop; transitions to ``paused``. */
export async function stopChecklistRun(
  checklistId: string,
  options: RequestOptions = {},
): Promise<AutoDriverRunOut> {
  return await postJson<AutoDriverRunOut>(
    `${apiChecklistRunEndpoint(checklistId)}/stop`,
    {},
    options,
  );
}

/** POST .../run/pause — alias of stop per behavior/checklists.md. */
export async function pauseChecklistRun(
  checklistId: string,
  options: RequestOptions = {},
): Promise<AutoDriverRunOut> {
  return await postJson<AutoDriverRunOut>(
    `${apiChecklistRunEndpoint(checklistId)}/pause`,
    {},
    options,
  );
}

/** POST .../run/resume — flip ``paused`` back to ``running``. */
export async function resumeChecklistRun(
  checklistId: string,
  options: RequestOptions = {},
): Promise<AutoDriverRunOut> {
  return await postJson<AutoDriverRunOut>(
    `${apiChecklistRunEndpoint(checklistId)}/resume`,
    {},
    options,
  );
}

/** POST .../run/skip-current — skip the in-flight item, advance. */
export async function skipCurrentChecklistRun(
  checklistId: string,
  options: RequestOptions = {},
): Promise<AutoDriverRunOut> {
  return await postJson<AutoDriverRunOut>(
    `${apiChecklistRunEndpoint(checklistId)}/skip-current`,
    {},
    options,
  );
}

// ``getChecklistRunStatus`` deliberately omitted — the
// :func:`getChecklistOverview` bundles the active-run row in one
// roundtrip and is the surface the ChecklistView consumes. The
// standalone .../run/status route exists; this file re-introduces the
// typed mirror when a consumer needs the narrower fetch.

// ---- Internal: PATCH / DELETE wrappers (the typed-fetch core only ----------
// ships GET / POST; PATCH + DELETE land here so the wider checklist surface
// keeps a single import surface for downstream stores.) -----------------------

const HTTP_OK_MIN = 200;
const HTTP_OK_MAX = 300;

async function patchJson<T>(path: string, body: unknown, options: RequestOptions = {}): Promise<T> {
  return await sendJson<T>("PATCH", path, body, options);
}

async function sendJson<T>(
  method: "PATCH" | "DELETE",
  path: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const url = options.query ? `${path}?${buildQuery(options.query)}` : path;
  const init: RequestInit = {
    method,
    headers: { Accept: "application/json" },
    signal: options.signal,
  };
  if (body !== null && body !== undefined) {
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const response = await fetch(url, init);
  if (response.status < HTTP_OK_MIN || response.status >= HTTP_OK_MAX) {
    const errBody = await safeReadBody(response);
    throw new ChecklistApiError(
      response.status,
      errBody,
      `${method} ${path} → ${response.status} ${response.statusText}`,
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  // Some PATCH endpoints return JSON; some DELETE endpoints return 204 with
  // an empty body. Read the body once via text() and parse only when present
  // so the caller can use the typed return without branching on the body.
  const text = await response.text();
  if (text === "") {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

function buildQuery(entries: Iterable<readonly [string, string]>): string {
  const params = new URLSearchParams();
  for (const [key, value] of entries) {
    params.append(key, value);
  }
  return params.toString();
}

async function safeReadBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    try {
      return await response.text();
    } catch {
      return null;
    }
  }
}

/**
 * Mirror of :class:`ApiError` with a distinct name so the checklist
 * surface's PATCH / DELETE failures don't shadow the GET / POST
 * surface from ``client.ts``. The fields are identical so callers
 * branch on ``error.status`` either way.
 */
export class ChecklistApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.name = "ChecklistApiError";
    this.status = status;
    this.body = body;
  }
}
