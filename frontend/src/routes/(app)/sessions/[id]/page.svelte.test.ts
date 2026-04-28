/**
 * Tests for the URL-bound session route at /sessions/[id]. The page is
 * the URL→state bridge: it reads `params.id` from the page store and
 * mirrors it into `sessions.selectedId` + drives `agent.connect`. A
 * direct paste of `/sessions/<deleted-id>` redirects to `/` once the
 * sessions list has loaded and confirms the id isn't there.
 *
 * The $app modules are aliased to local stubs in vitest.config.ts —
 * `setStubPage` lets tests drive the page store; `goto` is a vi.fn.
 */
import { cleanup, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { goto } from '$app/navigation';
import { setStubPage, resetStubPage } from '../../../../test-stubs/app/stores';
import type { Session } from '$lib/api';
import { agent } from '$lib/agent.svelte';
import { sessions } from '$lib/stores/sessions.svelte';
import SessionPage from './+page.svelte';

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

beforeEach(() => {
  // Stub fetches so any side-effect call (markViewed POST, etc.)
  // resolves cleanly without touching the network.
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      status: 200,
      async json() {
        return {};
      },
      async text() {
        return '{}';
      },
    }))
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.mocked(goto).mockClear();
  resetStubPage();
  sessions.list = [];
  sessions.selectedId = null;
  sessions.loading = false;
  sessions.error = null;
});

describe('/sessions/[id] route component', () => {
  it('mirrors params.id into sessions.selectedId on mount', async () => {
    sessions.list = [sess({ id: 'sess-a' })];
    setStubPage({ params: { id: 'sess-a' } });
    vi.spyOn(agent, 'connect').mockResolvedValue();

    render(SessionPage);

    await waitFor(() => expect(sessions.selectedId).toBe('sess-a'));
  });

  it('drives agent.connect for the URL id when not already connected', async () => {
    sessions.list = [sess({ id: 'sess-b' })];
    setStubPage({ params: { id: 'sess-b' } });
    const connectSpy = vi.spyOn(agent, 'connect').mockResolvedValue();

    render(SessionPage);

    await waitFor(() => expect(connectSpy).toHaveBeenCalledWith('sess-b'));
  });

  it('skips agent.connect when the agent is already on this session', async () => {
    sessions.list = [sess({ id: 'sess-c' })];
    setStubPage({ params: { id: 'sess-c' } });
    // Pretend the agent already opened this session — the route effect
    // must not trigger a redundant reconnect / WS handshake.
    agent.sessionId = 'sess-c';
    const connectSpy = vi.spyOn(agent, 'connect').mockResolvedValue();

    render(SessionPage);

    // Give effects a microtask to run.
    await Promise.resolve();
    await Promise.resolve();
    expect(connectSpy).not.toHaveBeenCalled();
    agent.sessionId = null; // reset for sibling tests
  });

  it('redirects to / when the URL id is not in the loaded sessions list', async () => {
    // List is loaded (loading=false, non-empty) but doesn't contain
    // 'gone' — direct paste of /sessions/gone after the row was
    // deleted elsewhere should bounce the user to the empty state.
    sessions.list = [sess({ id: 'still-here' })];
    sessions.loading = false;
    setStubPage({ params: { id: 'gone' } });
    vi.spyOn(agent, 'connect').mockResolvedValue();

    render(SessionPage);

    await waitFor(() => expect(goto).toHaveBeenCalledWith('/', { replaceState: true }));
  });

  it('does NOT redirect while the sessions list is still loading', async () => {
    // During boot, list is empty + loading=true. The redirect effect
    // must wait for the load to complete — otherwise a fresh page
    // load on /sessions/<id> would always bounce to / before its own
    // session row arrived.
    sessions.list = [];
    sessions.loading = true;
    setStubPage({ params: { id: 'sess-loading' } });
    vi.spyOn(agent, 'connect').mockResolvedValue();

    render(SessionPage);

    await Promise.resolve();
    await Promise.resolve();
    expect(goto).not.toHaveBeenCalled();
  });
});
