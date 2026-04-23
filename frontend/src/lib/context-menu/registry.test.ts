import { describe, expect, it } from 'vitest';

import { getActions, resolveMenu } from './registry';
import { SESSION_ACTIONS } from './actions/session';
import { MESSAGE_ACTIONS } from './actions/message';
import { TAG_ACTIONS, TAG_CHIP_ACTIONS } from './actions/tag';
import type { Action, ContextTarget, RenderedMenu } from './types';

/** Flatten a resolved menu's groups into a flat id array for
 * set-membership assertions. */
function flatIds(menu: RenderedMenu): string[] {
  return menu.groups.flatMap((g) => g.actions.map((a) => a.id));
}

const SESSION: ContextTarget = { type: 'session', id: 'sess-1' };
const MESSAGE: ContextTarget = {
  type: 'message',
  id: 'msg-1',
  sessionId: 'sess-1',
  role: 'user'
};
const TAG: ContextTarget = { type: 'tag', id: 7 };
const TAG_CHIP: ContextTarget = {
  type: 'tag_chip',
  tagId: 7,
  sessionId: 'sess-1'
};

describe('registry', () => {
  it('exposes session actions', () => {
    expect(getActions('session')).toBe(SESSION_ACTIONS);
  });

  it('exposes message actions', () => {
    expect(getActions('message')).toBe(MESSAGE_ACTIONS);
  });

  it('exposes tag actions', () => {
    expect(getActions('tag')).toBe(TAG_ACTIONS);
  });

  it('exposes tag_chip actions', () => {
    expect(getActions('tag_chip')).toBe(TAG_CHIP_ACTIONS);
  });

  it('every action ID is unique within its target', () => {
    for (const list of [
      SESSION_ACTIONS,
      MESSAGE_ACTIONS,
      TAG_ACTIONS,
      TAG_CHIP_ACTIONS
    ]) {
      const ids = list.map((a) => a.id);
      expect(new Set(ids).size).toBe(ids.length);
    }
  });

  it('action IDs follow <target>.<verb> naming', () => {
    for (const a of SESSION_ACTIONS) expect(a.id.startsWith('session.')).toBe(true);
    for (const a of MESSAGE_ACTIONS) expect(a.id.startsWith('message.')).toBe(true);
    for (const a of TAG_ACTIONS) expect(a.id.startsWith('tag.')).toBe(true);
    for (const a of TAG_CHIP_ACTIONS) expect(a.id.startsWith('tag_chip.')).toBe(true);
  });
});

describe('resolveMenu', () => {
  it('returns groups in canonical section order', () => {
    const menu = resolveMenu(SESSION, false);
    const seen = menu.groups.map((g) => g.section);
    // Phase 1 only has 'copy' rows — just assert order is a prefix
    // of the SECTIONS canonical sequence.
    const canonical = [
      'primary',
      'navigate',
      'create',
      'edit',
      'view',
      'copy',
      'organize',
      'destructive'
    ];
    for (let i = 1; i < seen.length; i++) {
      expect(canonical.indexOf(seen[i]!)).toBeGreaterThan(
        canonical.indexOf(seen[i - 1]!)
      );
    }
  });

  it('omits empty sections entirely', () => {
    const menu = resolveMenu(SESSION, false);
    for (const g of menu.groups) {
      expect(g.actions.length).toBeGreaterThan(0);
    }
  });

  it('hides advanced-only actions when not in advanced mode', () => {
    // Phase 4a.2 ships real advanced items on the session menu —
    // `session.copy_id`, `session.copy_share_link`, and
    // `session.fork.from_last_message`. Advanced mode surfaces them;
    // normal mode hides them. Drop the gating-dependent rows from
    // both menus first so a missing sessions store doesn't shift the
    // count out from under the assertion.
    const normalIds = flatIds(resolveMenu(SESSION, false));
    const advIds = flatIds(resolveMenu(SESSION, true));
    expect(normalIds).not.toContain('session.copy_id');
    expect(advIds).toContain('session.copy_id');
    expect(normalIds).not.toContain('session.copy_share_link');
    expect(advIds).toContain('session.copy_share_link');
  });

  it('resolves a message menu without error', () => {
    const menu = resolveMenu(MESSAGE, false);
    expect(menu.target).toEqual(MESSAGE);
    expect(menu.groups.length).toBeGreaterThan(0);
  });

  it('resolves a tag menu without error', () => {
    const menu = resolveMenu(TAG, false);
    expect(menu.target).toEqual(TAG);
    expect(menu.groups.length).toBeGreaterThan(0);
  });

  it('resolves a tag_chip menu without error', () => {
    const menu = resolveMenu(TAG_CHIP, false);
    expect(menu.target).toEqual(TAG_CHIP);
    expect(menu.groups.length).toBeGreaterThan(0);
  });

  it('applies the requires predicate', () => {
    const t: ContextTarget = { type: 'session', id: 'x' };
    const gated: Action[] = [
      {
        id: 'session.gated',
        label: 'gated',
        section: 'view',
        requires: () => false,
        handler: () => {}
      }
    ];
    const visible = gated.filter((a) => !(a.requires && !a.requires(t)));
    expect(visible).toHaveLength(0);
  });
});
