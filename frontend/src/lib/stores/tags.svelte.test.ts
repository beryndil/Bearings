import { afterEach, describe, expect, it, vi } from 'vitest';

import { tags } from './tags.svelte';

afterEach(() => {
  vi.restoreAllMocks();
  tags.list = [];
  tags.error = null;
  tags.loading = false;
});

function mockFetch(response: { ok: boolean; status?: number; body: unknown }): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: response.ok,
      status: response.status ?? (response.ok ? 200 : 500),
      async json() {
        return response.body;
      },
      async text() {
        return typeof response.body === 'string'
          ? response.body
          : JSON.stringify(response.body);
      }
    }))
  );
}

describe('tags store', () => {
  it('populates list on successful refresh', async () => {
    mockFetch({
      ok: true,
      body: [
        {
          id: 1,
          name: 'infra',
          color: null,
          pinned: true,
          sort_order: 0,
          created_at: '2026-04-19T00:00:00+00:00',
          session_count: 4
        }
      ]
    });
    await tags.refresh();
    expect(tags.error).toBeNull();
    expect(tags.list).toHaveLength(1);
    expect(tags.list[0].name).toBe('infra');
    expect(tags.list[0].pinned).toBe(true);
    expect(tags.loading).toBe(false);
  });

  it('records error text when the request fails', async () => {
    mockFetch({ ok: false, status: 500, body: 'boom' });
    await tags.refresh();
    expect(tags.error).toContain('500');
    expect(tags.list).toEqual([]);
    expect(tags.loading).toBe(false);
  });
});
