import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Session } from '$lib/api';
import { agent } from '$lib/agent.svelte';
import { checklists } from '$lib/stores/checklists.svelte';
import { sessions } from '$lib/stores/sessions.svelte';
import ChecklistView from './ChecklistView.svelte';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  sessions.list = [];
  sessions.selectedId = null;
  checklists.reset();
});

function session(overrides: Partial<Session> = {}): Session {
  return {
    id: 'sess-cl',
    created_at: '2026-04-21T00:00:00+00:00',
    updated_at: '2026-04-21T00:00:00+00:00',
    working_dir: '/tmp',
    model: 'claude-opus-4-7',
    title: 'Grocery run',
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
    kind: 'checklist',
    checklist_item_id: null,
    ...overrides
  };
}

type Fake = { ok: boolean; status?: number; body: unknown };

function queueResponses(queue: Fake[]): ReturnType<typeof vi.fn> {
  let i = 0;
  const stub = vi.fn(async () => {
    const r = queue[i++];
    if (!r) throw new Error(`unexpected fetch call #${i}`);
    return {
      ok: r.ok,
      status: r.status ?? (r.ok ? 200 : 500),
      async json() {
        return r.body;
      },
      async text() {
        return typeof r.body === 'string' ? r.body : JSON.stringify(r.body);
      }
    };
  });
  vi.stubGlobal('fetch', stub);
  return stub;
}

const EMPTY_CHECKLIST = {
  session_id: 'sess-cl',
  notes: null,
  created_at: '2026-04-21T00:00:00+00:00',
  updated_at: '2026-04-21T00:00:00+00:00',
  items: []
};

beforeEach(() => {
  sessions.list = [session()];
  sessions.selectedId = 'sess-cl';
});

describe('ChecklistView', () => {
  it('loads the checklist for the selected session and renders the add-item form', async () => {
    queueResponses([{ ok: true, body: EMPTY_CHECKLIST }]);
    render(ChecklistView);
    await waitFor(() => expect(checklists.current?.session_id).toBe('sess-cl'));
    // Add-item input rendered, Add button disabled while empty.
    await waitFor(() => {
      const btn = document.querySelector(
        'button[type="submit"]'
      ) as HTMLButtonElement | null;
      expect(btn).not.toBeNull();
      expect(btn!.disabled).toBe(true);
    });
  });

  it('optimistically renders a new item after Add', async () => {
    queueResponses([
      { ok: true, body: EMPTY_CHECKLIST },
      {
        ok: true,
        body: {
          id: 42,
          checklist_id: 'sess-cl',
          parent_item_id: null,
          label: 'Pick up milk',
          notes: null,
          checked_at: null,
          sort_order: 0,
          created_at: '2026-04-21T00:01:00+00:00',
          updated_at: '2026-04-21T00:01:00+00:00'
        }
      }
    ]);
    const { getByPlaceholderText, findByText } = render(ChecklistView);
    await waitFor(() => expect(checklists.current).not.toBeNull());

    const input = getByPlaceholderText('Add item…') as HTMLInputElement;
    await fireEvent.input(input, { target: { value: 'Pick up milk' } });
    await fireEvent.submit(input.closest('form')!);

    // Optimistic entry appears before the POST resolves; the
    // server-confirmed row arrives on the subsequent tick.
    await findByText('Pick up milk');
  });

  it('rolls back an optimistic add when the POST fails', async () => {
    queueResponses([
      { ok: true, body: EMPTY_CHECKLIST },
      { ok: false, status: 500, body: 'boom' }
    ]);
    const { getByPlaceholderText, queryByText } = render(ChecklistView);
    await waitFor(() => expect(checklists.current).not.toBeNull());

    const input = getByPlaceholderText('Add item…') as HTMLInputElement;
    await fireEvent.input(input, { target: { value: 'Ghost item' } });
    await fireEvent.submit(input.closest('form')!);

    // After the failure lands the store restores the previous
    // (empty) list, so the ghost label must disappear.
    await waitFor(() => expect(queryByText('Ghost item')).toBeNull());
    expect(checklists.error).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Slice 4: per-item paired-chat affordance
// ---------------------------------------------------------------------------

const CHECKLIST_WITH_ONE_ITEM = {
  session_id: 'sess-cl',
  notes: null,
  created_at: '2026-04-21T00:00:00+00:00',
  updated_at: '2026-04-21T00:00:00+00:00',
  items: [
    {
      id: 7,
      checklist_id: 'sess-cl',
      parent_item_id: null,
      label: 'Install deps',
      notes: null,
      checked_at: null,
      sort_order: 0,
      created_at: '2026-04-21T00:00:00+00:00',
      updated_at: '2026-04-21T00:00:00+00:00',
      chat_session_id: null
    }
  ]
};

const PAIRED_CHAT_SESSION = {
  id: 'chat-1',
  created_at: '2026-04-21T00:01:00+00:00',
  updated_at: '2026-04-21T00:01:00+00:00',
  working_dir: '/tmp',
  model: 'claude-opus-4-7',
  title: 'Install deps',
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
  checklist_item_id: 7
};

describe('ChecklistView paired-chat affordance', () => {
  it('clicking "Work on this" spawns a paired chat and selects it', async () => {
    queueResponses([
      { ok: true, body: CHECKLIST_WITH_ONE_ITEM },
      { ok: true, body: PAIRED_CHAT_SESSION }
    ]);
    const connectSpy = vi.spyOn(agent, 'connect').mockResolvedValue();
    const { getByRole } = render(ChecklistView);
    await waitFor(() => expect(checklists.current?.items.length).toBe(1));
    const btn = getByRole('button', { name: /Work on Install deps/ });
    await fireEvent.click(btn);
    await waitFor(() => expect(sessions.selectedId).toBe('chat-1'));
    // The newly-spawned chat must be in the sidebar list and the
    // agent runner must have been asked to connect. (The checklist
    // store itself is reset right after select() because the effect
    // detects `kind === 'chat'` — so the pairing pointer survives
    // in the sidebar's session row, not the checklist store.)
    expect(sessions.list.some((s) => s.id === 'chat-1')).toBe(true);
    expect(connectSpy).toHaveBeenCalledWith('chat-1');
  });

  it('renders "Continue working" affordance once the item is paired', async () => {
    const paired = {
      ...CHECKLIST_WITH_ONE_ITEM,
      items: [
        {
          ...CHECKLIST_WITH_ONE_ITEM.items[0],
          chat_session_id: 'chat-existing'
        }
      ]
    };
    queueResponses([{ ok: true, body: paired }]);
    const { getByRole, queryByRole } = render(ChecklistView);
    await waitFor(() => expect(checklists.current?.items.length).toBe(1));
    // "Continue working" button visible; "Work on" button is not.
    expect(getByRole('button', { name: /Continue working on Install deps/ })).toBeTruthy();
    expect(queryByRole('button', { name: /Work on Install deps/ })).toBeNull();
  });
});
