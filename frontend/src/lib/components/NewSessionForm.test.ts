import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { goto } from '$app/navigation';
import type { Tag } from '$lib/api';
import { sessions } from '$lib/stores/sessions.svelte';
import { tags } from '$lib/stores/tags.svelte';
import { preferences } from '$lib/stores/preferences.svelte';
import NewSessionForm from './NewSessionForm.svelte';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.mocked(goto).mockClear();
  sessions.list = [];
  sessions.selectedId = null;
  tags.list = [];
  tags.selected = [];
});

function tag(overrides: Partial<Tag> = {}): Tag {
  return {
    id: 1,
    name: 'infra',
    color: null,
    pinned: false,
    sort_order: 0,
    created_at: '2026-04-19T00:00:00+00:00',
    session_count: 0,
    open_session_count: 0,
    default_working_dir: null,
    default_model: null,
    tag_group: 'general',
    ...overrides,
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
      },
    };
  });
  vi.stubGlobal('fetch', stub);
  return stub;
}

beforeEach(() => {
  tags.list = [tag({ id: 1, name: 'infra' })];
  tags.selected = [1];
  // Seed the server-backed preferences row directly. The store
  // normally hydrates via `init()` against `/api/preferences`; tests
  // bypass that and write the in-memory row so the form's defaults
  // pick up the values without a fake-fetch round-trip.
  const row = (preferences as unknown as { row: Record<string, unknown> }).row;
  row.default_working_dir = '/tmp';
  row.default_model = 'claude-opus-4-7';
});

describe('NewSessionForm kind toggle', () => {
  it('hides Budget and Model inputs when Checklist is selected', async () => {
    const { getByRole, queryByPlaceholderText, queryByText } = render(NewSessionForm, {
      open: true,
    });
    // Chat is the default kind — Budget + Model both rendered.
    expect(queryByPlaceholderText('no cap')).not.toBeNull();
    expect(queryByText('Model')).not.toBeNull();

    const checklistBtn = getByRole('radio', { name: /Checklist/ });
    await fireEvent.click(checklistBtn);

    expect(queryByPlaceholderText('no cap')).toBeNull();
    expect(queryByText('Model')).toBeNull();
  });

  it("posts kind=checklist and navigates to the new session's URL on submit", async () => {
    const stub = queueResponses([
      {
        ok: true,
        body: {
          id: 'sess-new',
          created_at: '2026-04-21T00:00:00+00:00',
          updated_at: '2026-04-21T00:00:00+00:00',
          working_dir: '/tmp',
          model: 'claude-opus-4-7',
          title: null,
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
        },
      },
    ]);

    const { getByRole, getByLabelText } = render(NewSessionForm, {
      open: true,
    });
    // v0.20.6 made title required at the API boundary — fill it in
    // so the submit button isn't disabled.
    const titleInput = getByLabelText(/Title/) as HTMLInputElement;
    await fireEvent.input(titleInput, { target: { value: 'Daisy fixture' } });
    await fireEvent.click(getByRole('radio', { name: /Checklist/ }));
    await fireEvent.click(getByRole('button', { name: /Create session/ }));

    await waitFor(() => expect(stub).toHaveBeenCalledTimes(1));
    const [, init] = stub.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(body.kind).toBe('checklist');
    // §28 deep-link routing: the form navigates to /sessions/<id>
    // and the route component handles select + agent.connect via
    // its URL→state effect. Single goto means single connect — the
    // legacy double-fire race that motivated the prior "select-
    // before-connect" assertion is structurally impossible now.
    await waitFor(() => expect(goto).toHaveBeenCalledWith('/sessions/sess-new'));
  });

  it("chat submission also navigates to the new session's URL", async () => {
    const stub = queueResponses([
      {
        ok: true,
        body: {
          id: 'sess-chat',
          created_at: '2026-04-21T00:00:00+00:00',
          updated_at: '2026-04-21T00:00:00+00:00',
          working_dir: '/tmp',
          model: 'claude-opus-4-7',
          title: null,
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
        },
      },
    ]);

    const { getByRole, getByLabelText } = render(NewSessionForm, {
      open: true,
    });
    const titleInput = getByLabelText(/Title/) as HTMLInputElement;
    await fireEvent.input(titleInput, { target: { value: 'Daisy fixture' } });
    await fireEvent.click(getByRole('button', { name: /Create session/ }));

    await waitFor(() => expect(stub).toHaveBeenCalledTimes(1));
    const [, init] = stub.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(body.kind).toBe('chat');
    await waitFor(() => expect(goto).toHaveBeenCalledWith('/sessions/sess-chat'));
  });
});
