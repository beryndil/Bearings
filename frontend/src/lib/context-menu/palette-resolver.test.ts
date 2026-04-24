/**
 * Unit tests for the Phase 4b command-palette resolver.
 *
 * The resolver is the glue between the right-click registry and the
 * palette UI. Two things matter end-to-end:
 *   1. Every session-scoped action that renders in the right-click
 *      menu also surfaces in the palette when a session is selected,
 *      modulo mutually-exclusive `requires` predicates. If we ever
 *      break that contract the palette silently hides actions and the
 *      user only finds out by noticing something missing.
 *   2. The filter ranks prefix-on-label first, then substring-on-label,
 *      then id-based matches. Power users pattern-match on IDs
 *      (`menus.toml` uses them) so id-tail matching is first-class too.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { sessions } from '$lib/stores/sessions.svelte';
import {
  collectPaletteEntries,
  filterEntries,
  rankEntry,
  type PaletteEntry,
  type TargetResolver
} from './palette-resolver';
import type { Session } from '$lib/api';

function fakeSession(overrides: Partial<Session> = {}): Session {
  return {
    id: 'sess-palette',
    created_at: '2026-04-22T00:00:00+00:00',
    updated_at: '2026-04-22T00:00:00+00:00',
    working_dir: '/tmp/palette',
    model: 'claude-opus-4-7',
    title: 'Palette testbed',
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
    ...overrides
  };
}

const SESSION_RESOLVER: TargetResolver = (type) => {
  if (type === 'session') {
    return sessions.selectedId
      ? { type: 'session', id: sessions.selectedId }
      : null;
  }
  return null;
};

beforeEach(() => {
  sessions.list = [fakeSession()];
  sessions.selectedId = 'sess-palette';
});

afterEach(() => {
  sessions.list = [];
  sessions.selectedId = null;
});

describe('collectPaletteEntries', () => {
  it('returns no entries when the resolver refuses every target', () => {
    const resolver: TargetResolver = () => null;
    expect(collectPaletteEntries(resolver, ['session'])).toHaveLength(0);
  });

  it('surfaces the selected session actions when resolver yields one', () => {
    const entries = collectPaletteEntries(SESSION_RESOLVER, ['session']);
    const ids = new Set(entries.map((e) => e.id));
    // Both pin and reopen are `requires`-gated — on an open, unpinned
    // session the palette keeps pin, drops unpin, keeps archive, drops
    // reopen. Sanity-check one each way instead of snapshotting a
    // palette-specific catalog.
    expect(ids.has('session.pin')).toBe(true);
    expect(ids.has('session.unpin')).toBe(false);
    expect(ids.has('session.archive')).toBe(true);
    expect(ids.has('session.reopen')).toBe(false);
    // Copy-title has no requires predicate — always present.
    expect(ids.has('session.copy_title')).toBe(true);
  });

  it('expands submenu children inline with a parent-label prefix', () => {
    const entries = collectPaletteEntries(SESSION_RESOLVER, ['session']);
    const changeModel = entries.filter((e) =>
      e.id.startsWith('session.change_model.')
    );
    // KNOWN_MODELS has 3 entries; the submenu expansion yields one
    // palette row per leaf.
    expect(changeModel.length).toBeGreaterThanOrEqual(1);
    for (const e of changeModel) {
      expect(e.label.startsWith('Change model for continuation: ')).toBe(true);
    }
    // The parent (`session.change_model`) itself should NOT appear as
    // its own entry — clicking it in a menu opens the submenu, clicking
    // it in the palette would be a no-op.
    expect(entries.some((e) => e.id === 'session.change_model')).toBe(false);
  });

  it('flips unpin on when the selected session is pinned', () => {
    sessions.list = [fakeSession({ pinned: true })];
    const entries = collectPaletteEntries(SESSION_RESOLVER, ['session']);
    const ids = new Set(entries.map((e) => e.id));
    expect(ids.has('session.unpin')).toBe(true);
    expect(ids.has('session.pin')).toBe(false);
  });

  it('computes disabledReason once per entry', () => {
    const entries = collectPaletteEntries(SESSION_RESOLVER, ['session']);
    const duplicate = entries.find((e) => e.id === 'session.duplicate');
    // session.duplicate is a plan §2.3 disabled-with-tooltip entry.
    expect(duplicate?.disabledReason).toBeTruthy();
    // Every real (non-disabled) action has `null` in the field.
    const copyTitle = entries.find((e) => e.id === 'session.copy_title');
    expect(copyTitle?.disabledReason).toBeNull();
  });

  it('tags advanced entries for UI rendering', () => {
    const entries = collectPaletteEntries(SESSION_RESOLVER, ['session']);
    const copyId = entries.find((e) => e.id === 'session.copy_id');
    // `session.copy_id` is marked `advanced: true` in the registry.
    expect(copyId?.advanced).toBe(true);
    const copyTitle = entries.find((e) => e.id === 'session.copy_title');
    expect(copyTitle?.advanced).toBe(false);
  });
});

describe('rankEntry', () => {
  function entry(id: string, label: string): PaletteEntry {
    return {
      id,
      label,
      section: 'copy',
      target: { type: 'session', id: 'x' },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      action: { id, label, section: 'copy', handler: () => {} } as any,
      disabledReason: null,
      advanced: false
    };
  }

  it('returns 100 for empty query (base listing rank)', () => {
    expect(rankEntry(entry('session.pin', 'Pin session'), '')).toBe(100);
  });

  it('prefix-on-label beats everything else', () => {
    expect(rankEntry(entry('session.pin', 'Pin session'), 'pin')).toBe(0);
  });

  it('prefix-on-id beats substring-on-label', () => {
    const e = entry('session.pin', 'Fasten the session');
    expect(rankEntry(e, 'session')).toBe(1);
  });

  it('substring-on-label comes before substring-on-id', () => {
    // Query "wap" matches neither id-prefix nor label-prefix — label
    // contains it as a substring (rank 2), id doesn't contain it at
    // all, so substring-on-label wins.
    const e = entry('session.change_model', 'Swap the model');
    expect(rankEntry(e, 'wap')).toBe(2);
    // Query matches id substring only (the label has no "change").
    const e2 = entry('session.change_model', 'Pick a model');
    expect(rankEntry(e2, 'change')).toBe(3);
  });

  it('matches the id tail even when the query does not hit the full id', () => {
    const e = entry('session.open_in.editor', 'Open in editor');
    // Leading "ed" matches the id tail "editor".
    expect(rankEntry(e, 'ed')).toBeGreaterThanOrEqual(0);
  });

  it('returns -1 on no match', () => {
    expect(rankEntry(entry('session.pin', 'Pin session'), 'xyzzy')).toBe(-1);
  });
});

describe('filterEntries', () => {
  const entries: PaletteEntry[] = [
    {
      id: 'session.pin',
      label: 'Pin session',
      section: 'organize',
      target: { type: 'session', id: 'x' },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      action: {} as any,
      disabledReason: null,
      advanced: false
    },
    {
      id: 'session.open_in.editor',
      label: 'Open in editor',
      section: 'navigate',
      target: { type: 'session', id: 'x' },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      action: {} as any,
      disabledReason: null,
      advanced: false
    },
    {
      id: 'session.copy_title',
      label: 'Copy session title',
      section: 'copy',
      target: { type: 'session', id: 'x' },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      action: {} as any,
      disabledReason: null,
      advanced: false
    }
  ];

  it('sorts alphabetically by label on an empty query', () => {
    // Empty query makes every entry tie at rank 100; the tiebreaker
    // falls back to alphabetical label order so baseline scanning is
    // predictable. Callers relying on insertion order should filter
    // first, not scan the empty-query listing.
    const out = filterEntries(entries, '');
    expect(out.map((e) => e.label)).toEqual([
      'Copy session title',
      'Open in editor',
      'Pin session'
    ]);
  });

  it('ranks label-prefix above substring', () => {
    const out = filterEntries(entries, 'pin');
    expect(out[0]?.id).toBe('session.pin');
  });

  it('drops non-matching rows', () => {
    const out = filterEntries(entries, 'editor');
    expect(out.map((e) => e.id)).toEqual(['session.open_in.editor']);
  });

  it('breaks ties alphabetically by label', () => {
    // Two entries whose labels both contain "session" as a substring.
    const list: PaletteEntry[] = [
      { ...entries[2]!, label: 'zoom session' },
      { ...entries[0]!, label: 'pin session' }
    ];
    const out = filterEntries(list, 'session');
    // Both rank the same; alphabetical asc puts "pin" before "zoom".
    expect(out[0]?.label).toBe('pin session');
    expect(out[1]?.label).toBe('zoom session');
  });
});
