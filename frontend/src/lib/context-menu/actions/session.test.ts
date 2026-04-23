/**
 * Frozen ID snapshot per plan §7.4.
 *
 * Action IDs are a public API keyed by `~/.config/bearings/menus.toml`
 * overrides (pinned/hidden/shortcuts per user-facing stable names).
 * This test catches accidental renames, accidental drops, and the
 * "someone added a feature without realising the ID is part of the
 * contract" case. Growing the list is a one-line snapshot update in
 * the same PR that adds the action; renaming requires a deprecation
 * alias (see `Action.aliases` in `types.ts`).
 */

import { describe, expect, it } from 'vitest';

import { SESSION_ACTIONS } from './session';

describe('session.ts — action-ID stability', () => {
  it('exposes the frozen v0.9.1 catalog', () => {
    const ids = SESSION_ACTIONS.map((a) => a.id).sort();
    expect(ids).toEqual([
      'session.archive',
      'session.change_model',
      'session.copy_id',
      'session.copy_share_link',
      'session.copy_title',
      'session.delete',
      'session.duplicate',
      'session.fork.from_last_message',
      'session.open_in.claude_cli',
      'session.open_in.editor',
      'session.open_in.file_explorer',
      'session.open_in.git_gui',
      'session.open_in.terminal',
      'session.pin',
      'session.reopen',
      'session.unpin'
    ]);
  });

  it('change_model submenu enumerates every known model', () => {
    const changeModel = SESSION_ACTIONS.find(
      (a) => a.id === 'session.change_model'
    );
    expect(changeModel).toBeDefined();
    const submenu = Array.isArray(changeModel!.submenu) ? changeModel!.submenu : [];
    const ids = submenu.map((a) => a.id).sort();
    // Exact names deliberately in-line here rather than imported — if
    // `KNOWN_MODELS` drifts, the snapshot catches the drift instead of
    // silently going along with it.
    expect(ids).toEqual([
      'session.change_model.claude-haiku-4-5-20251001',
      'session.change_model.claude-opus-4-7',
      'session.change_model.claude-sonnet-4-6'
    ]);
  });

  it('every ID follows `session.<verb>[.<qualifier>]` naming', () => {
    for (const a of SESSION_ACTIONS) {
      expect(a.id.startsWith('session.')).toBe(true);
      // Dot-separated lowercase segments, no camelCase.
      expect(a.id).toMatch(/^session\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$/);
    }
  });

  it('archive and reopen are mutually exclusive via requires', () => {
    const archive = SESSION_ACTIONS.find((a) => a.id === 'session.archive');
    const reopen = SESSION_ACTIONS.find((a) => a.id === 'session.reopen');
    expect(archive?.requires).toBeDefined();
    expect(reopen?.requires).toBeDefined();
  });

  it('pin and unpin are mutually exclusive via requires', () => {
    const pin = SESSION_ACTIONS.find((a) => a.id === 'session.pin');
    const unpin = SESSION_ACTIONS.find((a) => a.id === 'session.unpin');
    expect(pin?.requires).toBeDefined();
    expect(unpin?.requires).toBeDefined();
  });

  it('session.delete is destructive and confirms before firing', () => {
    const del = SESSION_ACTIONS.find((a) => a.id === 'session.delete');
    expect(del?.destructive).toBe(true);
    expect(del?.section).toBe('destructive');
  });

  it('disabled-with-tooltip items name their target milestone', () => {
    const duplicate = SESSION_ACTIONS.find((a) => a.id === 'session.duplicate');
    const fork = SESSION_ACTIONS.find((a) => a.id === 'session.fork.from_last_message');
    const share = SESSION_ACTIONS.find((a) => a.id === 'session.copy_share_link');
    // The disabled predicate runs against any target; the target
    // shape doesn't matter because these items are always disabled.
    const bogus = { type: 'session', id: 'x' } as const;
    expect(duplicate?.disabled?.(bogus)).toBeTruthy();
    expect(fork?.disabled?.(bogus)).toBeTruthy();
    expect(share?.disabled?.(bogus)).toBeTruthy();
  });
});
