/**
 * Typed client for ``GET /api/sessions/{id}/messages`` and
 * ``GET /api/messages/{id}`` (item 1.9; ``src/bearings/web/routes/messages.py``).
 *
 * Mirrors :class:`bearings.web.models.messages.MessageOut` field for
 * field. The conversation pane fetches the full transcript on
 * session-select to hydrate the persisted history; live deltas
 * arrive over the per-session WebSocket plumbed in
 * ``src/bearings/web/streaming.py``.
 */
import { messageEndpoint, sessionMessagesEndpoint } from "../config";
import { getJson, type RequestOptions } from "./client";

/**
 * Wire shape for one message row — one-to-one with
 * :class:`bearings.web.models.messages.MessageOut`. Routing/usage
 * fields are nullable across all rows: only assistant rows persisted
 * by item 1.9's ``persist_assistant_turn`` carry real values.
 */
export interface MessageOut {
  id: string;
  session_id: string;
  role: string;
  content: string;
  created_at: string;
  // Spec §5 routing-decision projection.
  executor_model: string | null;
  advisor_model: string | null;
  effort_level: string | null;
  routing_source: string | null;
  routing_reason: string | null;
  matched_rule_id: number | null;
  // Spec §5 per-model usage projection.
  executor_input_tokens: number | null;
  executor_output_tokens: number | null;
  advisor_input_tokens: number | null;
  advisor_output_tokens: number | null;
  advisor_calls_count: number | null;
  cache_read_tokens: number | null;
  // Legacy flat carriers per spec §5 "Backfill for legacy data".
  input_tokens: number | null;
  output_tokens: number | null;
}

interface ListMessagesParams {
  /** Tail-window — return the last N messages. Omit for full transcript. */
  limit?: number;
  signal?: AbortSignal;
}

/**
 * List messages for ``sessionId`` in chronological order (oldest
 * first). 404 is surfaced via :class:`ApiError`.
 */
export async function listMessages(
  sessionId: string,
  params: ListMessagesParams = {},
): Promise<MessageOut[]> {
  const options: RequestOptions = {};
  if (params.limit !== undefined) {
    options.query = [["limit", String(params.limit)]];
  }
  if (params.signal !== undefined) {
    options.signal = params.signal;
  }
  return await getJson<MessageOut[]>(sessionMessagesEndpoint(sessionId), options);
}

/**
 * Fetch a single message by id. Used by the inspector "Why this
 * model?" panel (item 2.6) — included here so the messages-API
 * client surface in this item's scope mirrors the route module.
 */
export async function getMessage(
  messageId: string,
  options: RequestOptions = {},
): Promise<MessageOut> {
  return await getJson<MessageOut>(messageEndpoint(messageId), options);
}
