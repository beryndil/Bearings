/**
 * Frozen ID snapshot per plan §7.4.
 *
 * Multi-select IDs are the public API for `~/.config/bearings/menus.toml`
 * overrides — renames require a deprecation alias. The initial catalog
 * ships with v0.9.2 (Phase 9a).
 */

import { describe, expect, it } from 'vitest';

import { MULTI_SELECT_ACTIONS } from './multi_select';

describe('multi_select.ts — action-ID stability', () => {
  it('exposes the frozen v0.9.2 catalog', () => {
    const ids = MULTI_SELECT_ACTIONS.map((a) => a.id).sort();
    expect(ids).toEqual([
      'multi_select.clear',
      'multi_select.close',
      'multi_select.delete',
      'multi_select.export',
      'multi_select.tag',
      'multi_select.untag',
    ]);
  });

  it('every ID follows `multi_select.<verb>[.<qualifier>]` naming', () => {
    for (const a of MULTI_SELECT_ACTIONS) {
      expect(a.id.startsWith('multi_select.')).toBe(true);
      expect(a.id).toMatch(/^multi_select\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$/);
    }
  });

  it('delete is destructive and routes through the confirm store', () => {
    const del = MULTI_SELECT_ACTIONS.find((a) => a.id === 'multi_select.delete');
    expect(del?.destructive).toBe(true);
    expect(del?.section).toBe('destructive');
  });

  it('tag + untag actions expose function-form submenus', () => {
    const tag = MULTI_SELECT_ACTIONS.find((a) => a.id === 'multi_select.tag');
    const untag = MULTI_SELECT_ACTIONS.find((a) => a.id === 'multi_select.untag');
    expect(typeof tag?.submenu).toBe('function');
    expect(typeof untag?.submenu).toBe('function');
  });

  it('untag is gated behind Shift-right-click (advanced)', () => {
    const untag = MULTI_SELECT_ACTIONS.find((a) => a.id === 'multi_select.untag');
    expect(untag?.advanced).toBe(true);
  });

  it('clear lives under navigate, not destructive', () => {
    const clear = MULTI_SELECT_ACTIONS.find((a) => a.id === 'multi_select.clear');
    expect(clear?.section).toBe('navigate');
    expect(clear?.destructive).toBeUndefined();
  });
});
