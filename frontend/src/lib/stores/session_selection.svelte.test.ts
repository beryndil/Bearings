/**
 * Session multi-select store tests — Phase 9a of context-menu-plan.md.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import { sessionSelection } from './session_selection.svelte';

describe('SessionSelectionStore', () => {
  beforeEach(() => {
    sessionSelection.clear();
  });

  describe('toggle', () => {
    it('adds an id on first toggle', () => {
      sessionSelection.toggle('a');
      expect(sessionSelection.ids.has('a')).toBe(true);
      expect(sessionSelection.size).toBe(1);
      expect(sessionSelection.hasSelection).toBe(true);
    });

    it('removes an id on second toggle', () => {
      sessionSelection.toggle('a');
      sessionSelection.toggle('a');
      expect(sessionSelection.ids.size).toBe(0);
      expect(sessionSelection.hasSelection).toBe(false);
    });

    it('supports multiple ids in flight', () => {
      sessionSelection.toggle('a');
      sessionSelection.toggle('b');
      sessionSelection.toggle('c');
      expect(sessionSelection.size).toBe(3);
    });
  });

  describe('selectRange', () => {
    const order = ['a', 'b', 'c', 'd', 'e'];

    it('falls back to toggle when no anchor is set', () => {
      sessionSelection.selectRange('c', order);
      expect(sessionSelection.ids.has('c')).toBe(true);
      expect(sessionSelection.size).toBe(1);
    });

    it('selects inclusive range from anchor to target', () => {
      sessionSelection.toggle('b');
      sessionSelection.selectRange('d', order);
      expect([...sessionSelection.ids].sort()).toEqual(['b', 'c', 'd']);
    });

    it('handles reverse range (anchor > target)', () => {
      sessionSelection.toggle('d');
      sessionSelection.selectRange('b', order);
      expect([...sessionSelection.ids].sort()).toEqual(['b', 'c', 'd']);
    });

    it('degrades to single toggle when anchor is filtered out of view', () => {
      sessionSelection.toggle('z'); // not in order
      sessionSelection.selectRange('c', order);
      // anchor 'z' not in order → clickIndex >= 0, anchorIndex < 0 →
      // single toggle, 'z' is untouched, 'c' gets added
      expect(sessionSelection.ids.has('c')).toBe(true);
    });
  });

  describe('replace', () => {
    it('overwrites the current selection', () => {
      sessionSelection.toggle('a');
      sessionSelection.replace(['b', 'c']);
      expect([...sessionSelection.ids].sort()).toEqual(['b', 'c']);
    });

    it('clears the set when given an empty iterable', () => {
      sessionSelection.toggle('a');
      sessionSelection.replace([]);
      expect(sessionSelection.hasSelection).toBe(false);
    });
  });

  describe('drop', () => {
    it('removes a single id without resetting the anchor', () => {
      sessionSelection.toggle('a');
      sessionSelection.toggle('b');
      sessionSelection.drop('a');
      expect(sessionSelection.ids.has('a')).toBe(false);
      expect(sessionSelection.ids.has('b')).toBe(true);
    });

    it('is a no-op when the id is not selected', () => {
      sessionSelection.toggle('a');
      sessionSelection.drop('z');
      expect(sessionSelection.ids.has('a')).toBe(true);
    });
  });

  describe('clear', () => {
    it('empties the set', () => {
      sessionSelection.toggle('a');
      sessionSelection.toggle('b');
      sessionSelection.clear();
      expect(sessionSelection.size).toBe(0);
      expect(sessionSelection.hasSelection).toBe(false);
    });
  });
});
