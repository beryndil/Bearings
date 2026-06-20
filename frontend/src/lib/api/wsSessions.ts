/**
 * Sessions-broadcast WebSocket client (item 2.6).
 *
 * Connects to ``/ws/sessions`` and fans three message types to a
 * caller-supplied callback:
 *
 * - ``session_upsert`` — a session row was created or updated.
 * - ``session_delete`` — a session row was deleted.
 * - ``runner_state`` — a runner's is_running / is_awaiting_user
 *   changed.
 *
 * Auto-reconnects on close with capped exponential backoff so a
 * temporary server restart does not require a page reload.
 *
 * ``connectSessionsBroadcast`` returns an ``Unsubscribe`` callback.
 * Call it to stop reconnecting and close the active socket.
 */
import { WS_SESSIONS_PATH } from "../config";
import type { TagOut } from "./tags";
import type { SessionOut } from "./sessions";

/**
 * Live snapshot of one background workflow run.
 *
 * Emitted by the server's ``workflow_watcher`` polling task every
 * :data:`WORKFLOW_POLL_INTERVAL_S` seconds while the workflow journal
 * file exists and changes. The final event carries ``status`` set to
 * ``"completed"``, ``"killed"``, or ``"error"``.
 */
export interface WorkflowRunState {
  /** Bearings session id that owns this workflow run. */
  session_id: string;
  /** Harness run id — e.g. ``"wf_99657639-dbc"``. */
  run_id: string;
  /** Human-readable workflow name from the script's ``meta.name``. */
  workflow_name: string;
  /** Current lifecycle status: ``"running" | "completed" | "killed" | "error"``. */
  status: string;
  /** Title of the most recently started phase, or ``null`` before the first phase. */
  current_phase: string | null;
  /** Number of agents currently executing. */
  agents_running: number;
  /** Number of agents that have finished. */
  agents_done: number;
  /** Number of agents waiting to start. */
  agents_queued: number;
  /** Unix epoch in milliseconds when the workflow started. */
  started_at: number;
}

/** Union of all message types the sessions-broadcast channel emits. */
type SessionsBroadcastEvent =
  | { type: "session_upsert"; session: SessionOut }
  | { type: "session_delete"; session_id: string }
  | {
      type: "runner_state";
      session_id: string;
      is_running: boolean;
      is_awaiting_user: boolean;
      is_error: boolean;
    }
  | { type: "tag_upsert"; tag: TagOut }
  | { type: "tag_delete"; tag_id: number }
  | ({ type: "workflow_progress" } & WorkflowRunState);

type SessionsBroadcastHandler = (event: SessionsBroadcastEvent) => void;

/**
 * Optional connection-state callbacks for :func:`connectSessionsBroadcast`.
 *
 * Callers that need to track whether the sessions-broadcast WebSocket is
 * healthy (e.g. ``BackendStatusBanner``) supply these alongside the event
 * handler. Only the callbacks that are actually needed must be provided —
 * omitting a callback is always safe.
 */
interface SessionsBroadcastOptions {
  /** Called when the socket opens (or reconnects) successfully. */
  onOpen?: () => void;
  /**
   * Called when the socket closes. ``code`` is the WebSocket close code
   * (e.g. 4401 for auth failure, 1006 for abnormal closure).
   */
  onClose?: (code: number) => void;
  /** Called when the socket emits an error event. */
  onError?: () => void;
}

/** Remove the subscription and close the WebSocket. */
type Unsubscribe = () => void;

// Reconnect backoff: start at 500 ms, double on each attempt, cap at 30 s.
const _BACKOFF_INITIAL_MS = 500;
const _BACKOFF_FACTOR = 2;
const _BACKOFF_MAX_MS = 30_000;

/**
 * Open a ``/ws/sessions`` WebSocket and call ``onEvent`` for every
 * parsed :type:`SessionsBroadcastEvent`. Returns a cleanup function
 * that stops reconnecting and closes the socket.
 *
 * The heartbeat frames the server emits on idle are silently discarded
 * (they keep the connection alive but carry no session data).
 *
 * Optional ``options`` callbacks receive raw connection-state signals so
 * callers such as ``BackendStatusBanner`` can track reachability without
 * a second independent WebSocket.
 */
export function connectSessionsBroadcast(
  onEvent: SessionsBroadcastHandler,
  options?: SessionsBroadcastOptions,
): Unsubscribe {
  let stopped = false;
  let ws: WebSocket | null = null;
  let backoffMs = _BACKOFF_INITIAL_MS;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function buildUrl(): string {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}${WS_SESSIONS_PATH}`;
  }

  function connect(): void {
    if (stopped) {
      return;
    }
    ws = new WebSocket(buildUrl());

    ws.onmessage = (ev: MessageEvent<string>) => {
      const event = _parseFrame(ev.data);
      if (event !== null) {
        onEvent(event);
      }
    };

    ws.onopen = () => {
      backoffMs = _BACKOFF_INITIAL_MS;
      options?.onOpen?.();
    };

    ws.onclose = (ev: CloseEvent) => {
      ws = null;
      options?.onClose?.(ev.code);
      if (stopped) {
        return;
      }
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, backoffMs);
      backoffMs = Math.min(backoffMs * _BACKOFF_FACTOR, _BACKOFF_MAX_MS);
    };

    ws.onerror = () => {
      // ``onclose`` fires after ``onerror``; reconnect logic lives there.
      options?.onError?.();
    };
  }

  connect();

  return function unsubscribe(): void {
    stopped = true;
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws !== null) {
      ws.onclose = null;
      ws.close();
      ws = null;
    }
  };
}

/**
 * Parse one WebSocket text frame. Returns a
 * :type:`SessionsBroadcastEvent` on success, or ``null`` when the
 * frame is malformed or is a heartbeat ping (no action needed).
 */
function _parseFrame(text: string): SessionsBroadcastEvent | null {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const obj = raw as Record<string, unknown>;
  const type = obj.type;
  if (typeof type !== "string") {
    // Heartbeat frame has ``kind`` not ``type`` — silently drop.
    return null;
  }
  if (type === "session_upsert") {
    const session = obj.session;
    if (typeof session !== "object" || session === null) {
      return null;
    }
    return { type: "session_upsert", session: session as SessionOut };
  }
  if (type === "session_delete") {
    const session_id = obj.session_id;
    if (typeof session_id !== "string") {
      return null;
    }
    return { type: "session_delete", session_id };
  }
  if (type === "runner_state") {
    const session_id = obj.session_id;
    const is_running = obj.is_running;
    const is_awaiting_user = obj.is_awaiting_user;
    // is_error defaults to false for older server versions that omit the field.
    const is_error = typeof obj.is_error === "boolean" ? obj.is_error : false;
    if (
      typeof session_id !== "string" ||
      typeof is_running !== "boolean" ||
      typeof is_awaiting_user !== "boolean"
    ) {
      return null;
    }
    return { type: "runner_state", session_id, is_running, is_awaiting_user, is_error };
  }
  if (type === "tag_upsert") {
    const tag = obj.tag;
    if (typeof tag !== "object" || tag === null) {
      return null;
    }
    return { type: "tag_upsert", tag: tag as TagOut };
  }
  if (type === "tag_delete") {
    const tag_id = obj.tag_id;
    if (typeof tag_id !== "number") {
      return null;
    }
    return { type: "tag_delete", tag_id };
  }
  if (type === "workflow_progress") {
    const session_id = obj.session_id;
    const run_id = obj.run_id;
    const workflow_name = obj.workflow_name;
    const status = obj.status;
    if (
      typeof session_id !== "string" ||
      typeof run_id !== "string" ||
      typeof workflow_name !== "string" ||
      typeof status !== "string"
    ) {
      return null;
    }
    const current_phase = typeof obj.current_phase === "string" ? obj.current_phase : null;
    const agents_running = typeof obj.agents_running === "number" ? obj.agents_running : 0;
    const agents_done = typeof obj.agents_done === "number" ? obj.agents_done : 0;
    const agents_queued = typeof obj.agents_queued === "number" ? obj.agents_queued : 0;
    const started_at = typeof obj.started_at === "number" ? obj.started_at : 0;
    return {
      type: "workflow_progress",
      session_id,
      run_id,
      workflow_name,
      status,
      current_phase,
      agents_running,
      agents_done,
      agents_queued,
      started_at,
    };
  }
  return null;
}
