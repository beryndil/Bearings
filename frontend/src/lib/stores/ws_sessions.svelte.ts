import * as api from '$lib/api';
import { auth } from '$lib/stores/auth.svelte';
import { sessions } from '$lib/stores/sessions.svelte';

/**
 * Broadcast subscriber for the server-wide sessions-list WS channel.
 *
 * Unlike `AgentConnection` this socket is not per-session — it's one
 * connection per tab that streams `upsert | delete | runner_state`
 * frames for every session in the UI. Pairs with
 * `SessionsBroker` on the backend.
 *
 * Live path: the broadcast itself. Sub-second latency, no list-sized
 * fetch per tick. The Phase-2 cleanup (L6.1) retired the 3 s
 * `startRunningPoll` once the broadcast had a few months of clean
 * uptime; the broker still has no replay buffer, so reconnect
 * reconciliation lives here:
 *
 *   - `sessions.softRefresh()` reseeds the session list from
 *     `/api/sessions` — picks up upserts/deletes that landed while
 *     down or before this tab subscribed.
 *   - `sessions.runningSnapshot()` reseeds the `running` / `awaiting`
 *     indicator sets from `/api/sessions/{running,awaiting}` — covers
 *     sessions that were already mid-turn when the tab loaded, so the
 *     sidebar's orange/red dots aren't blind until the next state
 *     transition.
 *
 * Both fire on every successful open (fresh connect or reconnect).
 * Failures are silent — `runningSnapshot` preserves the last set and
 * the next live frame reconciles. Reconnect matches `AgentConnection`:
 * exponential backoff capped at 30 s.
 */

export type ConnectionState = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

const MAX_RETRY_DELAY_MS = 30_000;
const BASE_RETRY_DELAY_MS = 1_000;
const CODE_UNAUTHORIZED = 4401;

type UpsertFrame = { kind: 'upsert'; session: api.Session };
type DeleteFrame = { kind: 'delete'; session_id: string };
type RunnerStateFrame = {
  kind: 'runner_state';
  session_id: string;
  is_running: boolean;
  /** v0.10+ red-flashing axis. Optional because pre-0.10 broadcasters
   * omit the field; the reducer defaults it to false when absent so
   * rolling-deploy clients degrade gracefully. */
  is_awaiting_user?: boolean;
};
type SessionsWsFrame = UpsertFrame | DeleteFrame | RunnerStateFrame;

class SessionsWsConnection {
  state = $state<ConnectionState>('idle');
  lastCloseCode = $state<number | null>(null);

  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private retryCount = 0;
  private wantConnected = false;
  private openSocketImpl: () => WebSocket;

  constructor(openSocketImpl: () => WebSocket = api.openSessionsSocket) {
    this.openSocketImpl = openSocketImpl;
  }

  connect(): void {
    if (this.wantConnected && this.socket) return;
    this.wantConnected = true;
    this.retryCount = 0;
    this.lastCloseCode = null;
    this.openSocket();
  }

  close(): void {
    this.wantConnected = false;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.state = 'idle';
  }

  /** Apply a received frame to the sessions store. Exposed so tests
   * can exercise the reducer without spinning up a WebSocket. */
  handleFrame(frame: SessionsWsFrame): void {
    if (frame.kind === 'upsert') {
      sessions.applyUpsert(frame.session);
    } else if (frame.kind === 'delete') {
      sessions.applyDelete(frame.session_id);
    } else if (frame.kind === 'runner_state') {
      sessions.applyRunnerState(
        frame.session_id,
        frame.is_running,
        frame.is_awaiting_user ?? false
      );
    }
  }

  private openSocket(): void {
    this.state = 'connecting';
    const ws = this.openSocketImpl();
    this.socket = ws;

    const isCurrent = (): boolean => this.socket === ws;

    ws.addEventListener('open', () => {
      if (!isCurrent()) {
        ws.close();
        return;
      }
      this.state = 'open';
      this.retryCount = 0;
      // Reconcile once on every successful open (fresh or reconnect):
      //   - softRefresh — session list (upserts/deletes)
      //   - runningSnapshot — `running`/`awaiting` indicator sets
      // Both are silent on failure; the next live broadcast frame
      // reconciles any transient gap. See module header for the
      // full live-vs-snapshot story.
      void sessions.softRefresh();
      void sessions.runningSnapshot();
    });

    ws.addEventListener('message', (msg) => {
      if (!isCurrent()) return;
      try {
        const frame = JSON.parse(msg.data) as SessionsWsFrame;
        this.handleFrame(frame);
      } catch {
        // Malformed frame — drop it. A persistent problem surfaces as
        // an increasingly stale sidebar, which the poll tick repairs.
      }
    });

    ws.addEventListener('close', (ev) => {
      if (!isCurrent()) return;
      this.state = 'closed';
      this.lastCloseCode = ev.code;
      this.socket = null;
      if (ev.code === CODE_UNAUTHORIZED) {
        auth.markInvalid();
        this.wantConnected = false;
        return;
      }
      if (this.shouldReconnect(ev.code)) {
        this.scheduleReconnect();
      }
    });

    ws.addEventListener('error', () => {
      if (!isCurrent()) return;
      this.state = 'error';
    });
  }

  private shouldReconnect(code: number): boolean {
    // `wantConnected` is the single source of truth for client intent:
    // `close()` clears it before initiating a client-side teardown, so a
    // normal-close code (1000) that arrives while `wantConnected` is
    // still true can only mean the *server* or an intermediate proxy
    // dropped us — which is exactly the case we should reconnect from.
    // The prior guard against 1000 silently stranded the broadcast
    // channel for the rest of the tab's lifetime whenever a proxy idle
    // timeout or server shutdown cycled the socket, degrading the
    // sidebar to poll-only (3 s latency) without any surfaced error.
    // Auth failures (4401) still opt out — re-dialing won't fix a bad
    // token, and `auth.markInvalid()` is the recovery path there.
    return this.wantConnected && code !== CODE_UNAUTHORIZED;
  }

  private scheduleReconnect(): void {
    const delay = Math.min(BASE_RETRY_DELAY_MS * 2 ** this.retryCount, MAX_RETRY_DELAY_MS);
    this.retryCount += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      // Avoid spawning a parallel socket if a caller already reopened.
      if (this.socket) return;
      if (this.wantConnected) this.openSocket();
    }, delay);
  }
}

export const sessionsWs = new SessionsWsConnection();
// Exported class so tests can inject a socket factory.
export { SessionsWsConnection };
