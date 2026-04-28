/**
 * Tests for SessionsWsConnection — the broadcast subscriber for the
 * server-wide `/ws/sessions` channel introduced in Phase 2.
 *
 * We exercise the frame reducer directly via `handleFrame` so we don't
 * need to spin up a real WebSocket. The class exposes `handleFrame`
 * explicitly for this reason.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Session } from '$lib/api';
import { sessions } from './sessions.svelte';
import { SessionsWsConnection } from './ws_sessions.svelte';

afterEach(() => {
  vi.useRealTimers();
  sessions.list = [];
  sessions.selectedId = null;
  sessions.running = new Set();
  sessions.awaiting = new Set();
  sessions.filter = {};
});

function sess(overrides: Partial<Session> = {}): Session {
  return {
    id: 'sess-a',
    created_at: '2026-04-21T00:00:00+00:00',
    updated_at: '2026-04-21T00:00:00+00:00',
    working_dir: '/tmp/a',
    model: 'claude-opus-4-7',
    title: 'Alpha',
    description: null,
    max_budget_usd: null,
    total_cost_usd: 0,
    message_count: 0,
    session_instructions: null,
    permission_mode: null,
    last_context_pct: null,
    last_context_tokens: null,
    last_context_max: null,
    closed_at: null,
    kind: 'chat',
    checklist_item_id: null,
    last_completed_at: null,
    last_viewed_at: null,
    tag_ids: [],
    pinned: false,
    error_pending: false,
    ...overrides,
  };
}

describe('SessionsWsConnection.handleFrame', () => {
  // A fake factory keeps the tests off the real network — the ctor
  // still requires one even though we never call connect() here.
  const fakeSocketFactory = () => new EventTarget() as unknown as WebSocket;

  it('upsert frame patches the sessions store list and re-sorts', () => {
    sessions.list = [sess({ id: 'a', updated_at: '2026-04-22T10:00:00+00:00' })];
    const conn = new SessionsWsConnection(fakeSocketFactory);
    conn.handleFrame({
      kind: 'upsert',
      session: sess({ id: 'b', updated_at: '2026-04-22T11:00:00+00:00' }),
    });
    expect(sessions.list.map((s) => s.id)).toEqual(['b', 'a']);
  });

  it('delete frame drops the row and clears a matching selection', () => {
    sessions.list = [sess({ id: 'a' }), sess({ id: 'b' })];
    sessions.selectedId = 'a';
    const conn = new SessionsWsConnection(fakeSocketFactory);
    conn.handleFrame({ kind: 'delete', session_id: 'a' });
    expect(sessions.list.map((s) => s.id)).toEqual(['b']);
    expect(sessions.selectedId).toBeNull();
  });

  it('runner_state frame mutates the running set', () => {
    sessions.running = new Set();
    const conn = new SessionsWsConnection(fakeSocketFactory);
    conn.handleFrame({ kind: 'runner_state', session_id: 'a', is_running: true });
    expect(sessions.running.has('a')).toBe(true);
    conn.handleFrame({ kind: 'runner_state', session_id: 'a', is_running: false });
    expect(sessions.running.has('a')).toBe(false);
  });

  it('runner_state frame carries awaiting_user to the store', () => {
    sessions.running = new Set();
    sessions.awaiting = new Set();
    const conn = new SessionsWsConnection(fakeSocketFactory);
    conn.handleFrame({
      kind: 'runner_state',
      session_id: 'a',
      is_running: true,
      is_awaiting_user: true,
    });
    expect(sessions.running.has('a')).toBe(true);
    expect(sessions.awaiting.has('a')).toBe(true);
    conn.handleFrame({
      kind: 'runner_state',
      session_id: 'a',
      is_running: true,
      is_awaiting_user: false,
    });
    expect(sessions.awaiting.has('a')).toBe(false);
  });

  it('runner_state frame without is_awaiting_user defaults to not awaiting', () => {
    // Pre-0.10 broadcaster omits the field; reducer must not crash and
    // must clear any stale awaiting entry for this session.
    sessions.awaiting = new Set(['a']);
    const conn = new SessionsWsConnection(fakeSocketFactory);
    conn.handleFrame({ kind: 'runner_state', session_id: 'a', is_running: true });
    expect(sessions.awaiting.has('a')).toBe(false);
  });
});

/** Minimal WebSocket stand-in that records listener registration and
 * lets the test fire synthetic close events. Doesn't implement
 * `send` / readyState — the reconnect path doesn't exercise them. */
function makeFakeSocket() {
  const listeners: Record<string, ((ev: unknown) => void)[]> = {};
  return {
    addEventListener(name: string, fn: (ev: unknown) => void) {
      (listeners[name] ??= []).push(fn);
    },
    close() {},
    fire(name: string, ev: unknown) {
      for (const fn of listeners[name] ?? []) fn(ev);
    },
  } as unknown as WebSocket & { fire: (n: string, ev: unknown) => void };
}

describe('SessionsWsConnection reconnect policy', () => {
  it('reconnects after a clean close (1000) when the client still wants the channel', () => {
    vi.useFakeTimers();
    const opened: ReturnType<typeof makeFakeSocket>[] = [];
    const factory = () => {
      const s = makeFakeSocket();
      opened.push(s as unknown as ReturnType<typeof makeFakeSocket>);
      return s;
    };
    const conn = new SessionsWsConnection(factory);
    conn.connect();
    expect(opened.length).toBe(1);

    // Server (or a proxy) closes cleanly while the client still
    // wants the channel. Prior behavior: guard against code 1000 made
    // this a permanent teardown — sidebar fell back to poll-only for
    // the rest of the tab's lifetime. Current behavior: reconnect.
    (opened[0] as unknown as { fire: (n: string, ev: unknown) => void }).fire('close', {
      code: 1000,
    });

    // Exponential backoff starts at BASE_RETRY_DELAY_MS=1000; advance
    // past it to let the reconnect timer fire.
    vi.advanceTimersByTime(1_100);
    expect(opened.length).toBe(2);
  });

  it('does not reconnect after a close if close() was called first', () => {
    vi.useFakeTimers();
    const opened: ReturnType<typeof makeFakeSocket>[] = [];
    const factory = () => {
      const s = makeFakeSocket();
      opened.push(s as unknown as ReturnType<typeof makeFakeSocket>);
      return s;
    };
    const conn = new SessionsWsConnection(factory);
    conn.connect();
    conn.close(); // Client-initiated teardown → wantConnected=false.
    (opened[0] as unknown as { fire: (n: string, ev: unknown) => void }).fire('close', {
      code: 1000,
    });
    vi.advanceTimersByTime(5_000);
    expect(opened.length).toBe(1);
  });

  it('does not reconnect after a 4401 unauthorized close', () => {
    vi.useFakeTimers();
    const opened: ReturnType<typeof makeFakeSocket>[] = [];
    const factory = () => {
      const s = makeFakeSocket();
      opened.push(s as unknown as ReturnType<typeof makeFakeSocket>);
      return s;
    };
    const conn = new SessionsWsConnection(factory);
    conn.connect();
    (opened[0] as unknown as { fire: (n: string, ev: unknown) => void }).fire('close', {
      code: 4401,
    });
    vi.advanceTimersByTime(5_000);
    expect(opened.length).toBe(1);
  });
});
