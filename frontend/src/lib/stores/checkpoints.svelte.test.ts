import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Checkpoint, Session } from '$lib/api';
import { checkpoints } from './checkpoints.svelte';
import { sessions } from './sessions.svelte';

afterEach(() => {
  vi.restoreAllMocks();
  checkpoints._reset();
  sessions.list = [];
  sessions.selectedId = null;
});

type Fake = { ok: boolean; status?: number; body: unknown };

function cp(overrides: Partial<Checkpoint> & { id?: string } = {}): Checkpoint {
  // Suffix-only `id` overrides get the `cp-` prefix so tests read
  // naturally; full ids (`cp-foo`) pass through. Spread FIRST so the
  // prefixed id wins, else `...overrides` clobbers it.
  const { id: suffix, ...rest } = overrides;
  return {
    id: suffix ? (suffix.startsWith('cp-') ? suffix : `cp-${suffix}`) : 'cp-1',
    session_id: 's-1',
    message_id: 'm-1',
    label: null,
    created_at: '2026-04-22T00:00:00Z',
    ...rest
  };
}

function session(overrides: Partial<Session> = {}): Session {
  return {
    id: 's-fork',
    working_dir: '/tmp',
    model: 'claude-sonnet-4-6',
    title: 'fork',
    created_at: '2026-04-22T00:00:00Z',
    updated_at: '2026-04-22T00:00:00Z',
    closed_at: null,
    last_viewed_at: null,
    last_completed_at: null,
    message_count: 0,
    total_cost_usd: 0,
    pinned: false,
    error_pending: false,
    tag_ids: [],
    checklist_item_id: null,
    ...overrides
  } as Session;
}

/** Install a fetch stub that answers each request from a FIFO queue. */
function queueResponses(queue: Fake[]): void {
  let i = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
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
    })
  );
}

describe('checkpoints store', () => {
  it('load populates the cache for a session', async () => {
    queueResponses([
      { ok: true, body: [cp({ id: '1', label: 'mid' }), cp({ id: '2', label: 'end' })] }
    ]);
    await checkpoints.load('s-1');
    const list = checkpoints.forSession('s-1');
    expect(list).toHaveLength(2);
    expect(list[0].id).toBe('cp-1');
  });

  it('forSession returns [] for unknown sessions without fetching', () => {
    const list = checkpoints.forSession('never-loaded');
    expect(list).toEqual([]);
  });

  it('create prepends the new checkpoint to the cache', async () => {
    queueResponses([
      { ok: true, body: [cp({ id: '1' })] }, // load
      { ok: true, body: cp({ id: '2', label: 'fresh' }) } // create
    ]);
    await checkpoints.load('s-1');
    const created = await checkpoints.create('s-1', 'm-2', 'fresh');
    expect(created?.id).toBe('cp-2');
    const list = checkpoints.forSession('s-1');
    expect(list.map((c) => c.id)).toEqual(['cp-2', 'cp-1']);
  });

  it('remove is optimistic and restores on server failure', async () => {
    queueResponses([
      { ok: true, body: [cp({ id: '1' })] }, // load
      { ok: false, status: 500, body: 'boom' } // delete fails
    ]);
    await checkpoints.load('s-1');
    const removed = await checkpoints.remove('s-1', 'cp-1');
    expect(removed).toBe(false);
    // Restored after the server error
    expect(checkpoints.forSession('s-1').map((c) => c.id)).toEqual(['cp-1']);
  });

  it('remove drops the row on a 204', async () => {
    queueResponses([
      { ok: true, body: [cp({ id: '1' }), cp({ id: '2' })] }, // load
      { ok: true, status: 204, body: null } // delete OK
    ]);
    await checkpoints.load('s-1');
    const removed = await checkpoints.remove('s-1', 'cp-1');
    expect(removed).toBe(true);
    expect(checkpoints.forSession('s-1').map((c) => c.id)).toEqual(['cp-2']);
  });

  it('fork upserts the new session into the sessions store', async () => {
    queueResponses([
      { ok: true, body: session({ id: 's-fork', title: 'branch' }) }
    ]);
    const forked = await checkpoints.fork('s-1', 'cp-1');
    expect(forked?.id).toBe('s-fork');
    expect(sessions.list.some((s) => s.id === 's-fork')).toBe(true);
  });

  it('forget drops the cache entry for a session', async () => {
    queueResponses([{ ok: true, body: [cp({ id: '1' })] }]);
    await checkpoints.load('s-1');
    expect(checkpoints.forSession('s-1')).toHaveLength(1);
    checkpoints.forget('s-1');
    expect(checkpoints.forSession('s-1')).toEqual([]);
  });
});
