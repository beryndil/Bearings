/**
 * L4.3.2 — Reply-actions client. Calls the SSE endpoint
 * `POST /api/sessions/{id}/invoke_reply_action/{messageId}` and yields
 * parsed events to a callback. Wave 2 lane 2 of the assistant-reply
 * action row; backs the `✂ TLDR` modal (and L4.3.3's `⚔ CRIT`).
 *
 * We can't use the spec's `EventSource` because it doesn't support
 * Authorization headers (Bearings runs bearer auth via headers, not
 * query strings — see core.ts). Instead we POST with `fetch` and
 * stream-decode the response body manually. The wire format is the
 * stock SSE shape: frames separated by `\n\n`, lines `event: X`,
 * `data: <json>`, comments starting with `:`. Comments are dropped;
 * the rest reaches the consumer as a typed event.
 *
 * The cancel handle returned by `streamReplyAction` aborts the in-
 * flight request when the user closes the modal mid-stream — the
 * server detects the disconnect and tears down the SDK client.
 */

import type { Session } from './sessions';

/** One incremental text chunk from the sub-agent. The modal appends
 * `text` to its rendered preview as each chunk arrives. */
export type ReplyActionToken = { type: 'token'; text: string };

/** Terminal success event. `cost_usd` may be null if the SDK didn't
 * report one (synthetic completions, older SDK versions); `full_text`
 * carries the joined preview body for the modal's "Send to composer"
 * + "Copy" actions so they don't have to re-stitch from chunks. */
export type ReplyActionComplete = {
  type: 'complete';
  cost_usd: number | null;
  full_text: string;
};

/** Terminal failure event. `message` is the human-readable error;
 * the modal renders it in red. */
export type ReplyActionError = { type: 'error'; message: string };

export type ReplyActionEvent = ReplyActionToken | ReplyActionComplete | ReplyActionError;

/** Mirrors the backend's `ACTION_LABELS` dict. Adding `critique` in
 * L4.3.3 only needs a new entry on the server side; the catalog
 * endpoint feeds the frontend at runtime. */
export type ReplyActionCatalogEntry = { label: string };
export type ReplyActionCatalog = Record<string, ReplyActionCatalogEntry>;

const TOKEN_STORAGE_KEY = 'bearings:token';

function readAuthToken(): string | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

function authHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  };
  const token = readAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export async function fetchReplyActionsCatalog(
  fetchImpl: typeof fetch = fetch
): Promise<ReplyActionCatalog> {
  const res = await fetchImpl('/api/sessions/reply_actions/catalog', {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`GET catalog → ${res.status}: ${body}`);
  }
  return (await res.json()) as ReplyActionCatalog;
}

/** Handle returned by `streamReplyAction`. `cancel()` aborts the
 * in-flight fetch and closes the response body — the server sees
 * the disconnect and tears down its SDK client. `done` resolves
 * after the stream terminates (cleanly or with an abort). */
export type ReplyActionStreamHandle = {
  cancel: () => void;
  done: Promise<void>;
};

export type StreamReplyActionOpts = {
  /** Override the parent session's model. Optional. */
  model?: string;
  /** Test seam for the underlying fetch. Production callers omit. */
  fetchImpl?: typeof fetch;
};

/** Start an SSE stream for a reply-action invocation. `onEvent` is
 * called for each parsed event (token / complete / error). The
 * promise resolves when the stream ends — either because the server
 * sent a terminal event, the network closed, or `cancel()` was
 * called. `onEvent` is guaranteed to fire at most once with a
 * `complete` or `error` payload; an aborted stream resolves without
 * a terminal event so the caller can treat cancel as a non-terminal
 * close.
 *
 * Implementation detail: we use `fetch` + `response.body.getReader()`
 * because `EventSource` can't carry an Authorization header, and the
 * frame parser is small enough that an inline implementation beats
 * pulling a polyfill. Buffer up to one frame at a time; flush on
 * the spec's `\n\n` terminator. */
export function streamReplyAction(
  sessionId: string,
  messageId: string,
  action: string,
  onEvent: (ev: ReplyActionEvent) => void,
  opts: StreamReplyActionOpts = {}
): ReplyActionStreamHandle {
  const fetchImpl = opts.fetchImpl ?? fetch;
  const controller = new AbortController();
  const body: Record<string, string> = { action };
  if (opts.model) body.model = opts.model;
  const done = (async () => {
    try {
      const res = await fetchImpl(`/api/sessions/${sessionId}/invoke_reply_action/${messageId}`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!res.ok) {
        const errBody = await res.text().catch(() => '');
        onEvent({
          type: 'error',
          message: `HTTP ${res.status}: ${errBody || res.statusText || 'request failed'}`,
        });
        return;
      }
      if (!res.body) {
        onEvent({ type: 'error', message: 'no response body' });
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      while (true) {
        const { value, done: streamDone } = await reader.read();
        if (streamDone) break;
        buffer += decoder.decode(value, { stream: true });
        // Frames are `\n\n`-separated. Drain every complete one and
        // leave the trailing partial in the buffer.
        let sep = buffer.indexOf('\n\n');
        while (sep !== -1) {
          const frame = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          const parsed = parseFrame(frame);
          if (parsed) onEvent(parsed);
          sep = buffer.indexOf('\n\n');
        }
      }
    } catch (err) {
      // AbortError = caller hit cancel(); silent. Anything else
      // surfaces as a wire-level error event.
      const isAbort = err instanceof DOMException && err.name === 'AbortError';
      if (!isAbort) {
        onEvent({
          type: 'error',
          message: err instanceof Error ? err.message : String(err),
        });
      }
    }
  })();
  return {
    cancel: () => controller.abort(),
    done,
  };
}

/** Parse one SSE frame (sans trailing `\n\n`). Returns null for
 * comment-only frames, malformed frames, or events we don't
 * recognise. The server is the only producer so we trust its
 * wire shape — but we still gate on the `event:` line so an
 * older client talking to a newer server doesn't crash on a
 * future event type. */
function parseFrame(frame: string): ReplyActionEvent | null {
  let eventName = '';
  let dataRaw = '';
  for (const line of frame.split('\n')) {
    if (line.startsWith(':')) continue; // comment
    if (line.startsWith('event:')) {
      eventName = line.slice('event:'.length).trim();
    } else if (line.startsWith('data:')) {
      dataRaw = line.slice('data:'.length).trim();
    }
  }
  if (!eventName) return null;
  let data: unknown;
  try {
    data = dataRaw ? JSON.parse(dataRaw) : {};
  } catch {
    return null;
  }
  if (eventName === 'token' && isObj(data) && typeof data.text === 'string') {
    return { type: 'token', text: data.text };
  }
  if (
    eventName === 'complete' &&
    isObj(data) &&
    (typeof data.cost_usd === 'number' || data.cost_usd === null) &&
    typeof data.full_text === 'string'
  ) {
    return {
      type: 'complete',
      cost_usd: data.cost_usd as number | null,
      full_text: data.full_text,
    };
  }
  if (eventName === 'error' && isObj(data) && typeof data.message === 'string') {
    return { type: 'error', message: data.message };
  }
  return null;
}

function isObj(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

// Re-export Session for ergonomic imports from this module's consumers.
export type { Session };
