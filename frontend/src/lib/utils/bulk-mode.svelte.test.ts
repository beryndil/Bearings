import { describe, it, expect, beforeEach } from 'vitest';

import { BulkModeController } from './bulk-mode.svelte';
import type * as api from '$lib/api';

function msg(id: string, role: 'user' | 'assistant' = 'user'): api.Message {
  return {
    id,
    role,
    content: `m${id}`,
    thinking: null,
    created_at: '0',
    session_id: 's1'
  };
}

describe('BulkModeController', () => {
  let bm: BulkModeController;
  let all: api.Message[];

  beforeEach(() => {
    bm = new BulkModeController();
    all = ['a', 'b', 'c', 'd', 'e'].map((id) => msg(id));
  });

  it('starts inactive with empty selection', () => {
    expect(bm.active).toBe(false);
    expect(bm.count).toBe(0);
    expect(bm.ids()).toEqual([]);
    expect(bm.lastSelectedId).toBeNull();
  });

  it('toggle() flips active state and clears on exit', () => {
    bm.toggle();
    expect(bm.active).toBe(true);
    bm.toggleSelect(all[0], false, all);
    expect(bm.count).toBe(1);
    bm.toggle();
    expect(bm.active).toBe(false);
    expect(bm.count).toBe(0);
    expect(bm.lastSelectedId).toBeNull();
  });

  it('clear() empties selection without changing active', () => {
    bm.toggle();
    bm.toggleSelect(all[0], false, all);
    bm.toggleSelect(all[1], false, all);
    expect(bm.count).toBe(2);
    bm.clear();
    expect(bm.active).toBe(true);
    expect(bm.count).toBe(0);
    expect(bm.lastSelectedId).toBeNull();
  });

  it('plain click toggles a single id and updates anchor', () => {
    bm.toggleSelect(all[2], false, all);
    expect(bm.ids()).toEqual(['c']);
    expect(bm.lastSelectedId).toBe('c');
    bm.toggleSelect(all[4], false, all);
    expect(bm.ids().sort()).toEqual(['c', 'e']);
    expect(bm.lastSelectedId).toBe('e');
  });

  it('clicking an already-selected id deselects it', () => {
    bm.toggleSelect(all[0], false, all);
    bm.toggleSelect(all[0], false, all);
    expect(bm.count).toBe(0);
    expect(bm.lastSelectedId).toBe('a');
  });

  it('shift-click extends a range from the anchor (forward)', () => {
    bm.toggleSelect(all[1], false, all); // anchor = b
    bm.toggleSelect(all[3], true, all); // shift to d
    expect(bm.ids().sort()).toEqual(['b', 'c', 'd']);
    expect(bm.lastSelectedId).toBe('d');
  });

  it('shift-click extends a range from the anchor (backward)', () => {
    bm.toggleSelect(all[3], false, all); // anchor = d
    bm.toggleSelect(all[1], true, all); // shift to b
    expect(bm.ids().sort()).toEqual(['b', 'c', 'd']);
    expect(bm.lastSelectedId).toBe('b');
  });

  it('shift-click without a prior anchor falls back to single toggle', () => {
    bm.toggleSelect(all[2], true, all);
    expect(bm.ids()).toEqual(['c']);
    expect(bm.lastSelectedId).toBe('c');
  });

  it('shift-click adds to existing selection without clobbering it', () => {
    bm.toggleSelect(all[0], false, all); // a selected, anchor a
    bm.toggleSelect(all[3], true, all); // shift to d → a..d range
    expect(bm.ids().sort()).toEqual(['a', 'b', 'c', 'd']);
  });

  it('selectedIds is a fresh Set on every change (reactivity contract)', () => {
    bm.toggleSelect(all[0], false, all);
    const first = bm.selectedIds;
    bm.toggleSelect(all[1], false, all);
    expect(bm.selectedIds).not.toBe(first);
  });

  it('shift-click against a missing anchor (off-list id) falls back', () => {
    bm.lastSelectedId = 'phantom';
    bm.toggleSelect(all[2], true, all);
    expect(bm.ids()).toEqual(['c']);
  });

  it('count tracks selectedIds size', () => {
    bm.toggleSelect(all[0], false, all);
    bm.toggleSelect(all[1], false, all);
    bm.toggleSelect(all[4], true, all);
    expect(bm.count).toBe(bm.selectedIds.size);
  });
});
