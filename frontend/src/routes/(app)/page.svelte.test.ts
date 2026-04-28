/**
 * Tests for the root `/` route. Three behaviors:
 *  1. Renders an empty-state pane.
 *  2. Redirects ?session=<id> → /sessions/<id> (legacy bookmark
 *     compatibility).
 *  3. Restores the remembered last-selected session from localStorage
 *     when the user lands fresh on `/`, but only if they didn't just
 *     navigate here from an active session.
 */
import { cleanup, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { goto } from '$app/navigation';
import { setStubPage, resetStubPage } from '../../test-stubs/app/stores';
import type { Session } from '$lib/api';
import { sessions } from '$lib/stores/sessions.svelte';
import RootPage from './+page.svelte';

function sess(overrides: Partial<Session> = {}): Session {
  return {
    id: 'sess-r',
    created_at: '2026-04-21T00:00:00+00:00',
    updated_at: '2026-04-21T00:00:00+00:00',
    working_dir: '/tmp/r',
    model: 'claude-opus-4-7',
    title: 'Remembered',
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
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      status: 200,
      async json() {
        return [];
      },
      async text() {
        return '[]';
      },
    }))
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.mocked(goto).mockClear();
  resetStubPage();
  localStorage.clear();
  sessions.list = [];
  sessions.selectedId = null;
  sessions.loading = false;
  sessions.error = null;
});

describe('root / route component', () => {
  it('renders the empty-state pane when no redirect fires', async () => {
    const { getByTestId } = render(RootPage);
    expect(getByTestId('root-empty-state').textContent).toMatch(/Pick a session/i);
  });

  it('redirects ?session=<id> to /sessions/<id>', async () => {
    setStubPage({
      url: new URL('http://localhost/?session=legacy-abc'),
    });
    render(RootPage);
    await waitFor(() =>
      expect(goto).toHaveBeenCalledWith('/sessions/legacy-abc', {
        replaceState: true,
      })
    );
  });

  it('restores the remembered session when entering / fresh with the row in the list', async () => {
    localStorage.setItem('bearings:selectedSessionId', 'sess-r');
    sessions.list = [sess({ id: 'sess-r' })];
    sessions.loading = false;
    sessions.selectedId = null;

    render(RootPage);

    await waitFor(() =>
      expect(goto).toHaveBeenCalledWith('/sessions/sess-r', {
        replaceState: true,
      })
    );
  });

  it('does NOT restore when the user just navigated /sessions/abc → /', async () => {
    // Discriminator: selectedId is non-null at mount means the user
    // came from a deep-linked session and explicitly walked to /.
    // Bouncing them back would defeat the navigation intent.
    localStorage.setItem('bearings:selectedSessionId', 'sess-r');
    sessions.list = [sess({ id: 'sess-r' })];
    sessions.loading = false;
    sessions.selectedId = 'sess-r'; // user just left this session

    render(RootPage);

    // Effects flush — and the redirect must NOT fire.
    await Promise.resolve();
    await Promise.resolve();
    expect(goto).not.toHaveBeenCalled();
  });

  it('does NOT restore when the remembered session is no longer in the open list', async () => {
    // Remembered id was deleted or closed elsewhere — restore would
    // dump the user into /sessions/<id> which immediately bounces
    // back. Better to render the empty state and let them pick.
    localStorage.setItem('bearings:selectedSessionId', 'sess-deleted');
    sessions.list = [sess({ id: 'still-here' })];
    sessions.loading = false;
    sessions.selectedId = null;

    render(RootPage);

    await Promise.resolve();
    await Promise.resolve();
    expect(goto).not.toHaveBeenCalled();
  });
});
