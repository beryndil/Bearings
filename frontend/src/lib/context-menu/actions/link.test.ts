/**
 * Frozen ID snapshot per plan §7.4 for the link target.
 *
 * All four actions ship live in Phase 6. `link.open_in.editor` is
 * gated by a `disabled` predicate that greys it on non-file:// URLs —
 * kept visible so the menu geometry stays stable across right-clicks.
 */

import { describe, expect, it } from 'vitest';

import { LINK_ACTIONS } from './link';
import type { ContextTarget } from '../types';

const HTTP_LINK: ContextTarget = {
  type: 'link',
  href: 'https://example.com/page',
  text: 'example',
  sessionId: 's-1',
  messageId: 'm-1',
};

const FILE_LINK: ContextTarget = {
  type: 'link',
  href: 'file:///tmp/demo.py',
  text: 'demo.py',
  sessionId: 's-1',
  messageId: 'm-1',
};

const BAD_LINK: ContextTarget = {
  type: 'link',
  href: 'not a url at all',
  text: 'broken',
  sessionId: null,
  messageId: null,
};

describe('link.ts — action-ID stability', () => {
  it('exposes the frozen v0.9.1 catalog', () => {
    const ids = LINK_ACTIONS.map((a) => a.id).sort();
    expect(ids).toEqual([
      'link.copy_text',
      'link.copy_url',
      'link.open_in.editor',
      'link.open_new_tab',
    ]);
  });

  it('every ID follows `link.<verb>[.<qualifier>]` naming', () => {
    for (const a of LINK_ACTIONS) {
      expect(a.id.startsWith('link.')).toBe(true);
      expect(a.id).toMatch(/^link\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$/);
    }
  });

  it('copy actions have no action-level disabled predicate', () => {
    for (const id of ['link.copy_url', 'link.copy_text']) {
      const action = LINK_ACTIONS.find((a) => a.id === id);
      expect(action?.disabled).toBeUndefined();
    }
  });

  it('open_new_tab is live (no disabled predicate)', () => {
    const action = LINK_ACTIONS.find((a) => a.id === 'link.open_new_tab');
    expect(action?.disabled).toBeUndefined();
    expect(typeof action?.handler).toBe('function');
  });

  it('open_in.editor greys on http URLs, enables on file:// URLs', () => {
    const editor = LINK_ACTIONS.find((a) => a.id === 'link.open_in.editor');
    expect(editor?.disabled?.(HTTP_LINK)).toBeTruthy();
    expect(editor?.disabled?.(FILE_LINK)).toBeFalsy();
    // Malformed URLs never resolve to a file path — the predicate
    // must not throw and must grey the row.
    expect(editor?.disabled?.(BAD_LINK)).toBeTruthy();
  });

  it('copy_text is advanced (Shift-right-click) and copy_url is not', () => {
    const copyUrl = LINK_ACTIONS.find((a) => a.id === 'link.copy_url');
    const copyText = LINK_ACTIONS.find((a) => a.id === 'link.copy_text');
    expect(copyUrl?.advanced).toBeFalsy();
    expect(copyText?.advanced).toBe(true);
  });
});
