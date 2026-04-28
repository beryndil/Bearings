/**
 * Integration test for Ctrl+Shift+P command palette.
 *
 * Verifies the end-to-end flow: open the palette with a selected
 * session, observe registry-derived entries appear, filter via the
 * input, fire a handler via Enter. The registry actions make real
 * calls to the sessions store's mutation methods when fired, so those
 * methods are stubbed to assert invocation without hitting fetch.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';

import type { Session } from '$lib/api';
import { palette } from '$lib/context-menu/palette.svelte';
import { sessions } from '$lib/stores/sessions.svelte';
import CommandPalette from './CommandPalette.svelte';

function sess(overrides: Partial<Session> = {}): Session {
  return {
    id: 'sess-p',
    created_at: '2026-04-22T00:00:00+00:00',
    updated_at: '2026-04-22T00:00:00+00:00',
    working_dir: '/tmp',
    model: 'claude-opus-4-7',
    title: 'Palette session',
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
  sessions.list = [sess()];
  sessions.selectedId = 'sess-p';
  palette.hide();
});

afterEach(() => {
  cleanup();
  palette.hide();
  vi.restoreAllMocks();
  sessions.list = [];
  sessions.selectedId = null;
});

describe('CommandPalette', () => {
  it('renders nothing while the store is closed', () => {
    const { queryByTestId } = render(CommandPalette);
    expect(queryByTestId('command-palette')).toBeNull();
  });

  it('renders registry-derived rows when opened', async () => {
    const { getByTestId, queryAllByTestId } = render(CommandPalette);
    palette.show();
    await waitFor(() => expect(getByTestId('command-palette')).toBeTruthy());
    const rows = queryAllByTestId('command-palette-row');
    // Session menu has ~14-15 visible rows once submenu leaves expand
    // and gating drops one of each mutually-exclusive pair. An exact
    // count would couple this test to the action catalog; checking
    // non-empty + one sentinel row keeps it robust.
    expect(rows.length).toBeGreaterThan(5);
    const ids = rows.map((r) => r.getAttribute('data-action-id'));
    expect(ids).toContain('session.pin');
    expect(ids).toContain('session.copy_title');
  });

  it('filters rows as the user types', async () => {
    const { getByTestId, queryAllByTestId } = render(CommandPalette);
    palette.show();
    await waitFor(() => expect(getByTestId('command-palette')).toBeTruthy());
    const input = getByTestId('command-palette-query') as HTMLInputElement;
    await fireEvent.input(input, { target: { value: 'archive' } });
    await waitFor(() => {
      const rows = queryAllByTestId('command-palette-row');
      const ids = rows.map((r) => r.getAttribute('data-action-id'));
      // Filter should leave only matches for "archive".
      expect(ids).toContain('session.archive');
      expect(ids).not.toContain('session.pin');
    });
  });

  it('Escape closes the palette', async () => {
    const { getByTestId, queryByTestId } = render(CommandPalette);
    palette.show();
    await waitFor(() => expect(getByTestId('command-palette')).toBeTruthy());
    await fireEvent.keyDown(getByTestId('command-palette'), { key: 'Escape' });
    await waitFor(() => expect(queryByTestId('command-palette')).toBeNull());
    expect(palette.open).toBe(false);
  });

  it('Enter fires the top-ranked handler and hides the palette', async () => {
    const spy = vi.spyOn(sessions, 'update').mockResolvedValue(null);
    const { getByTestId, queryByTestId } = render(CommandPalette);
    palette.show();
    await waitFor(() => expect(getByTestId('command-palette')).toBeTruthy());
    const input = getByTestId('command-palette-query') as HTMLInputElement;
    // "pin" ranks `session.pin` as the top row (label prefix match).
    await fireEvent.input(input, { target: { value: 'pin' } });
    await fireEvent.keyDown(getByTestId('command-palette'), { key: 'Enter' });
    await waitFor(() => expect(queryByTestId('command-palette')).toBeNull());
    expect(spy).toHaveBeenCalledWith('sess-p', { pinned: true });
  });

  it('renders an empty-state hint when no session is selected', async () => {
    sessions.selectedId = null;
    const { getByTestId } = render(CommandPalette);
    palette.show();
    await waitFor(() => expect(getByTestId('command-palette')).toBeTruthy());
    const list = getByTestId('command-palette-list');
    expect(list.textContent).toMatch(/Open a session/i);
  });

  it('greys disabled rows and refuses to fire on Enter', async () => {
    const spy = vi.spyOn(sessions, 'update').mockResolvedValue(null);
    const { getByTestId } = render(CommandPalette);
    palette.show();
    await waitFor(() => expect(getByTestId('command-palette')).toBeTruthy());
    const input = getByTestId('command-palette-query') as HTMLInputElement;
    // `session.duplicate` is permanently disabled per §2.3 until the
    // primitive lands — firing it must be a no-op.
    await fireEvent.input(input, { target: { value: 'duplicate' } });
    await fireEvent.keyDown(getByTestId('command-palette'), { key: 'Enter' });
    expect(spy).not.toHaveBeenCalled();
  });
});
