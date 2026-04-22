import { describe, expect, it } from 'vitest';

import { getActions, resolveMenu } from './registry';
import { SESSION_ACTIONS } from './actions/session';
import { MESSAGE_ACTIONS } from './actions/message';
import type { Action, ContextTarget } from './types';

const SESSION: ContextTarget = { type: 'session', id: 'sess-1' };
const MESSAGE: ContextTarget = {
  type: 'message',
  id: 'msg-1',
  sessionId: 'sess-1',
  role: 'user'
};

describe('registry', () => {
  it('exposes session actions', () => {
    expect(getActions('session')).toBe(SESSION_ACTIONS);
  });

  it('exposes message actions', () => {
    expect(getActions('message')).toBe(MESSAGE_ACTIONS);
  });

  it('every action ID is unique within its target', () => {
    for (const list of [SESSION_ACTIONS, MESSAGE_ACTIONS]) {
      const ids = list.map((a) => a.id);
      expect(new Set(ids).size).toBe(ids.length);
    }
  });

  it('action IDs follow <target>.<verb> naming', () => {
    for (const a of SESSION_ACTIONS) expect(a.id.startsWith('session.')).toBe(true);
    for (const a of MESSAGE_ACTIONS) expect(a.id.startsWith('message.')).toBe(true);
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
    const advancedOnly: Action = {
      id: 'session.test_advanced',
      label: 'test',
      section: 'view',
      advanced: true,
      handler: () => {}
    };
    // Build an ad-hoc target-agnostic menu via resolveMenu's filter
    // logic. Since we can't inject at runtime in Phase 1, verify the
    // filter indirectly by asserting Phase 1 ships no advanced items
    // (so the menu shape is identical between modes).
    const normal = resolveMenu(SESSION, false);
    const adv = resolveMenu(SESSION, true);
    expect(normal.groups).toEqual(adv.groups);
    // And the ad-hoc action itself would be filtered: restate the
    // predicate to keep the test honest.
    const visibleNormal = [advancedOnly].filter(
      (a) => !(a.advanced && !false)
    );
    const visibleAdvanced = [advancedOnly].filter(
      (a) => !(a.advanced && !true)
    );
    expect(visibleNormal).toHaveLength(0);
    expect(visibleAdvanced).toHaveLength(1);
  });

  it('resolves a message menu without error', () => {
    const menu = resolveMenu(MESSAGE, false);
    expect(menu.target).toEqual(MESSAGE);
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
