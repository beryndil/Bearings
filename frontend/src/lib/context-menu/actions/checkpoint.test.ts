/**
 * Frozen ID snapshot per plan §7.4.
 *
 * Checkpoint IDs are the public API for `~/.config/bearings/menus.toml`
 * overrides — renames require a deprecation alias. The initial catalog
 * ships with v0.9.2 (Phase 7.3).
 */

import { describe, expect, it } from 'vitest';

import { CHECKPOINT_ACTIONS } from './checkpoint';
import type { CheckpointTarget } from '../types';

const LIVE: CheckpointTarget = {
  type: 'checkpoint',
  id: 'cp-1',
  sessionId: 's-1',
  messageId: 'm-1',
  label: 'midpoint',
};

const ORPHAN: CheckpointTarget = {
  type: 'checkpoint',
  id: 'cp-2',
  sessionId: 's-1',
  messageId: null,
  label: 'stranded',
};

const UNLABELLED: CheckpointTarget = {
  type: 'checkpoint',
  id: 'cp-3',
  sessionId: 's-1',
  messageId: 'm-3',
  label: null,
};

describe('checkpoint.ts — action-ID stability', () => {
  it('exposes the frozen v0.9.2 catalog', () => {
    const ids = CHECKPOINT_ACTIONS.map((a) => a.id).sort();
    expect(ids).toEqual([
      'checkpoint.copy_id',
      'checkpoint.copy_label',
      'checkpoint.delete',
      'checkpoint.fork',
    ]);
  });

  it('every ID follows `checkpoint.<verb>[.<qualifier>]` naming', () => {
    for (const a of CHECKPOINT_ACTIONS) {
      expect(a.id.startsWith('checkpoint.')).toBe(true);
      expect(a.id).toMatch(/^checkpoint\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$/);
    }
  });

  it('fork is the primary action, delete is destructive', () => {
    const fork = CHECKPOINT_ACTIONS.find((a) => a.id === 'checkpoint.fork');
    const del = CHECKPOINT_ACTIONS.find((a) => a.id === 'checkpoint.delete');
    expect(fork?.section).toBe('primary');
    expect(del?.destructive).toBe(true);
    expect(del?.section).toBe('destructive');
  });

  it('fork is disabled for orphaned checkpoints, enabled for live', () => {
    const fork = CHECKPOINT_ACTIONS.find((a) => a.id === 'checkpoint.fork');
    expect(fork?.disabled?.(LIVE)).toBeNull();
    expect(fork?.disabled?.(ORPHAN)).toBeTruthy();
  });

  it('copy_label is disabled when label is null or empty', () => {
    const copy = CHECKPOINT_ACTIONS.find((a) => a.id === 'checkpoint.copy_label');
    expect(copy?.disabled?.(LIVE)).toBeNull();
    expect(copy?.disabled?.(UNLABELLED)).toBeTruthy();
  });

  it('copy_id is advanced (Shift-right-click)', () => {
    const copyId = CHECKPOINT_ACTIONS.find((a) => a.id === 'checkpoint.copy_id');
    expect(copyId?.advanced).toBe(true);
  });
});
