/**
 * Typed client for the reply-actions API surface (T1-09).
 *
 * Two endpoints:
 * - ``GET /api/reply_actions/catalog`` — static list of available transformations.
 * - ``POST /api/sessions/{id}/reply_actions`` — apply a transformation to a message body.
 *
 * Per Exec-2A spec: catalog ids are ``"summarize"``, ``"reformat"``,
 * ``"translate_plain"``, ``"extract_key_points"``. The apply endpoint
 * is session-scoped (404 when the session does not exist).
 */
import { API_BASE } from "../config";
import { getJson, postJson, type RequestOptions } from "./client";

/** Base path for the reply-actions catalog. */
const API_REPLY_ACTIONS_CATALOG_ENDPOINT = `${API_BASE}/reply_actions/catalog`;

/**
 * One entry from the reply-actions catalog — mirrors
 * :class:`bearings.web.routes.reply_actions.ActionDescriptor`.
 */
export interface ActionDescriptor {
  /** Stable catalog id (``"summarize"`` | ``"reformat"`` | etc.). */
  id: string;
  /** Human-readable label rendered on the action button. */
  label: string;
  /** One-line description rendered as tooltip / sub-text. */
  description: string;
  /** Instruction injected into the LLM advisor call. Not displayed. */
  instruction: string;
}

/**
 * Request body for ``POST /api/sessions/{id}/reply_actions`` — mirrors
 * :class:`bearings.web.routes.reply_actions.ApplyActionIn`.
 */
interface ApplyActionIn {
  /** The message text to transform (min_length=1). */
  source_content: string;
  /** Catalog id of the transformation to apply. */
  transformation_id: string;
  /**
   * When ``true``, the server inserts the transformed content as a
   * follow-up system message on the session. Defaults to ``false``.
   * In v1 the insertion is a no-op; the ``inserted`` flag in the
   * response is always ``false``.
   */
  insert_follow_up?: boolean;
}

/**
 * Response body for ``POST /api/sessions/{id}/reply_actions`` — mirrors
 * :class:`bearings.web.routes.reply_actions.ApplyActionOut`.
 */
export interface ApplyActionOut {
  /** Transformed content returned by the advisor. */
  content: string;
  /** Echo of the requested catalog id. */
  transformation_id: string;
  /** ``true`` when the result was inserted as a follow-up message. */
  inserted: boolean;
}

/**
 * Fetch the static reply-action catalog.
 *
 * Returns at least 3 entries: ``summarize``, ``reformat``,
 * ``translate_plain``, ``extract_key_points``.
 *
 * @throws :class:`ApiError` on 5xx.
 */
export async function getReplyActionCatalog(
  options: RequestOptions = {},
): Promise<ActionDescriptor[]> {
  return await getJson<ActionDescriptor[]>(API_REPLY_ACTIONS_CATALOG_ENDPOINT, options);
}

/**
 * Apply a transformation to ``body.source_content`` via the LLM advisor.
 *
 * @throws :class:`ApiError` on 404 (session not found), 422 (unknown
 *   transformation_id), 501 (advisor not configured), 502 (advisor call
 *   failed), or 5xx.
 */
export async function applyReplyAction(
  sessionId: string,
  body: ApplyActionIn,
  options: RequestOptions = {},
): Promise<ApplyActionOut> {
  const path = `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/reply_actions`;
  return await postJson<ApplyActionOut>(path, body, options);
}
