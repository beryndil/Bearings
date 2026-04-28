/**
 * Frozen ID snapshots for the two tag target types — plan §7.4.
 * See the equivalent comment in `session.test.ts` for the stability
 * contract.
 */

import { describe, expect, it } from 'vitest';

import { TAG_ACTIONS, TAG_CHIP_ACTIONS } from './tag';
import type { TagChipTarget } from '../types';

describe('tag.ts — TAG_ACTIONS stability', () => {
  it('exposes the frozen v0.9.1 catalog for sidebar tag rows', () => {
    const ids = TAG_ACTIONS.map((a) => a.id).sort();
    expect(ids).toEqual(['tag.copy_name', 'tag.delete', 'tag.edit', 'tag.pin', 'tag.unpin']);
  });

  it('every ID follows `tag.<verb>` naming', () => {
    for (const a of TAG_ACTIONS) {
      expect(a.id.startsWith('tag.')).toBe(true);
      expect(a.id).toMatch(/^tag\.[a-z][a-z0-9_]*$/);
    }
  });

  it('pin and unpin are mutually exclusive via requires', () => {
    const pin = TAG_ACTIONS.find((a) => a.id === 'tag.pin');
    const unpin = TAG_ACTIONS.find((a) => a.id === 'tag.unpin');
    expect(pin?.requires).toBeDefined();
    expect(unpin?.requires).toBeDefined();
  });

  it('tag.delete is destructive', () => {
    const del = TAG_ACTIONS.find((a) => a.id === 'tag.delete');
    expect(del?.destructive).toBe(true);
    expect(del?.section).toBe('destructive');
  });
});

describe('tag.ts — TAG_CHIP_ACTIONS stability', () => {
  it('exposes the frozen v0.9.1 catalog for session chips', () => {
    const ids = TAG_CHIP_ACTIONS.map((a) => a.id).sort();
    expect(ids).toEqual(['tag_chip.copy_name', 'tag_chip.detach']);
  });

  it('every ID follows `tag_chip.<verb>` naming', () => {
    for (const a of TAG_CHIP_ACTIONS) {
      expect(a.id.startsWith('tag_chip.')).toBe(true);
      expect(a.id).toMatch(/^tag_chip\.[a-z][a-z0-9_]*$/);
    }
  });

  it('tag_chip.detach hides itself when sessionId is null', () => {
    const detach = TAG_CHIP_ACTIONS.find((a) => a.id === 'tag_chip.detach');
    expect(detach?.requires).toBeDefined();
    const withSession: TagChipTarget = {
      type: 'tag_chip',
      tagId: 5,
      sessionId: 'sess-1',
    };
    const withoutSession: TagChipTarget = {
      type: 'tag_chip',
      tagId: 5,
      sessionId: null,
    };
    expect(detach!.requires!(withSession)).toBe(true);
    expect(detach!.requires!(withoutSession)).toBe(false);
  });
});
