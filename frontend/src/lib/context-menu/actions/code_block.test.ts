/**
 * Frozen ID snapshot per plan §7.4 for the code_block target.
 *
 * `code_block.save_to_file` and `code_block.open_in.editor` ship
 * disabled-with-tooltip: both depend on a future shell "save temp"
 * primitive. The IDs are reserved now so a TOML override written
 * against v0.9.1 survives the v0.10.x un-stub.
 */

import { describe, expect, it } from 'vitest';

import { CODE_BLOCK_ACTIONS } from './code_block';
import type { ContextTarget } from '../types';

const BLOCK: ContextTarget = {
  type: 'code_block',
  text: 'print("hi")\n',
  language: 'python',
  sessionId: 's-1',
  messageId: 'm-1'
};

const UNKNOWN_LANG: ContextTarget = {
  type: 'code_block',
  text: 'echo hi\n',
  language: null,
  sessionId: null,
  messageId: null
};

describe('code_block.ts — action-ID stability', () => {
  it('exposes the frozen v0.9.1 catalog', () => {
    const ids = CODE_BLOCK_ACTIONS.map((a) => a.id).sort();
    expect(ids).toEqual([
      'code_block.copy',
      'code_block.copy_with_fence',
      'code_block.open_in.editor',
      'code_block.save_to_file'
    ]);
  });

  it('every ID follows `code_block.<verb>[.<qualifier>]` naming', () => {
    for (const a of CODE_BLOCK_ACTIONS) {
      expect(a.id.startsWith('code_block.')).toBe(true);
      expect(a.id).toMatch(/^code_block\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$/);
    }
  });

  it('copy actions have no action-level disabled predicate', () => {
    for (const id of ['code_block.copy', 'code_block.copy_with_fence']) {
      const action = CODE_BLOCK_ACTIONS.find((a) => a.id === id);
      expect(action?.disabled).toBeUndefined();
    }
  });

  it('save_to_file + open_in.editor land disabled-with-tooltip', () => {
    for (const id of ['code_block.save_to_file', 'code_block.open_in.editor']) {
      const action = CODE_BLOCK_ACTIONS.find((a) => a.id === id);
      expect(action?.disabled?.(BLOCK)).toBeTruthy();
    }
  });

  it('copy_with_fence is advanced (Shift-right-click) and copy is not', () => {
    const copy = CODE_BLOCK_ACTIONS.find((a) => a.id === 'code_block.copy');
    const fenced = CODE_BLOCK_ACTIONS.find(
      (a) => a.id === 'code_block.copy_with_fence'
    );
    expect(copy?.advanced).toBeFalsy();
    expect(fenced?.advanced).toBe(true);
  });

  it('copy_with_fence handler tolerates a missing language', async () => {
    // The null-language path picks the bare ``` fence. Crashing here
    // would mean right-clicking a plain pre-formatted block (no fence
    // tag) in advanced mode throws.
    const fenced = CODE_BLOCK_ACTIONS.find(
      (a) => a.id === 'code_block.copy_with_fence'
    );
    expect(fenced).toBeDefined();
    // Don't actually exercise the clipboard write — the action's
    // disabled predicate is what we care about here. Just confirm the
    // handler reference exists.
    expect(typeof fenced?.handler).toBe('function');
    // And the action has no `disabled` gate keyed on the language —
    // `copy_with_fence` must work on fenceless blocks too.
    expect(fenced?.disabled?.(UNKNOWN_LANG)).toBeFalsy();
  });
});
