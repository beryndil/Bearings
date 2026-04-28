/**
 * Frozen ID snapshot per plan §7.4 — Phase 16 of docs/context-menu-plan.md.
 */

import { describe, expect, it } from 'vitest';

import { PENDING_OPERATION_ACTIONS } from './pending_operation';
import type { PendingOperationTarget } from '../types';

const WITH_COMMAND: PendingOperationTarget = {
  type: 'pending_operation',
  name: 'fix-lockfile',
  directory: '/home/dave/Projects/Bearings',
  command: 'uv lock --upgrade',
  description: 'Lockfile drift detected',
};

const WITHOUT_COMMAND: PendingOperationTarget = {
  type: 'pending_operation',
  name: 'review-todo',
  directory: '/home/dave/Projects/Bearings',
  command: null,
  description: 'Backlog review pending',
};

describe('pending_operation.ts — action-ID stability', () => {
  it('exposes the frozen v0.16.0 catalog', () => {
    const ids = PENDING_OPERATION_ACTIONS.map((a) => a.id).sort();
    expect(ids).toEqual([
      'pending_operation.copy_command',
      'pending_operation.copy_name',
      'pending_operation.dismiss',
      'pending_operation.open_in.editor',
      'pending_operation.resolve',
    ]);
  });

  it('every ID follows `pending_operation.<verb>[.<qualifier>]` naming', () => {
    for (const a of PENDING_OPERATION_ACTIONS) {
      expect(a.id.startsWith('pending_operation.')).toBe(true);
      expect(a.id).toMatch(/^pending_operation\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$/);
    }
  });

  it('resolve is primary, dismiss is destructive', () => {
    const resolve = PENDING_OPERATION_ACTIONS.find((a) => a.id === 'pending_operation.resolve');
    const dismiss = PENDING_OPERATION_ACTIONS.find((a) => a.id === 'pending_operation.dismiss');
    expect(resolve?.section).toBe('primary');
    expect(dismiss?.destructive).toBe(true);
  });

  it('copy_command is disabled when no command is attached', () => {
    const copy = PENDING_OPERATION_ACTIONS.find((a) => a.id === 'pending_operation.copy_command');
    expect(copy?.disabled?.(WITH_COMMAND)).toBeNull();
    expect(copy?.disabled?.(WITHOUT_COMMAND)).toBeTruthy();
  });
});
