/**
 * Palette-store unit tests.
 *
 * The store is intentionally small — open/hide/toggle + a query string.
 * These tests nail the two behaviours I don't want to regress:
 *   - `show()` always starts with a cleared query, so a previous
 *     filter doesn't carry across opens.
 *   - `toggle()` flips symmetrically. Tests don't exercise the
 *     Ctrl+Shift+P keybinding because that binding lives in
 *     `+page.svelte`, not the store.
 */

import { afterEach, describe, expect, it } from 'vitest';

import { palette } from './palette.svelte';

afterEach(() => {
  palette.hide();
});

describe('palette store', () => {
  it('starts hidden with an empty query', () => {
    expect(palette.open).toBe(false);
    expect(palette.query).toBe('');
  });

  it('show opens and clears the query', () => {
    palette.query = 'stale text';
    palette.show();
    expect(palette.open).toBe(true);
    expect(palette.query).toBe('');
  });

  it('hide closes and clears the query', () => {
    palette.show();
    palette.query = 'something';
    palette.hide();
    expect(palette.open).toBe(false);
    expect(palette.query).toBe('');
  });

  it('toggle flips symmetrically', () => {
    expect(palette.open).toBe(false);
    palette.toggle();
    expect(palette.open).toBe(true);
    palette.toggle();
    expect(palette.open).toBe(false);
  });
});
