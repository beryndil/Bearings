/**
 * Frozen ID snapshot per plan §7.4 for the tool_call target.
 *
 * `tool_call.retry` stays in the catalog (disabled-with-tooltip) so
 * the public ID is reserved from day one — changing it later would
 * invalidate any TOML override users have hand-rolled.
 */

import { describe, expect, it } from 'vitest';

import { TOOL_CALL_ACTIONS } from './tool_call';
import type { ContextTarget } from '../types';

const CALL: ContextTarget = {
  type: 'tool_call',
  id: 'tc-1',
  sessionId: 's-1',
  messageId: 'a-1',
};

describe('tool_call.ts — action-ID stability', () => {
  it('exposes the frozen v0.9.1 catalog', () => {
    const ids = TOOL_CALL_ACTIONS.map((a) => a.id).sort();
    expect(ids).toEqual([
      'tool_call.copy.id',
      'tool_call.copy.input',
      'tool_call.copy.name',
      'tool_call.copy.output',
      'tool_call.retry',
    ]);
  });

  it('every ID follows `tool_call.<verb>[.<qualifier>]` naming', () => {
    for (const a of TOOL_CALL_ACTIONS) {
      expect(a.id.startsWith('tool_call.')).toBe(true);
      expect(a.id).toMatch(/^tool_call\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$/);
    }
  });

  it('retry lands disabled-with-tooltip', () => {
    const retry = TOOL_CALL_ACTIONS.find((a) => a.id === 'tool_call.retry');
    expect(retry?.disabled?.(CALL)).toBeTruthy();
    expect(retry?.advanced).toBe(true);
  });

  it('copy actions are live (no disabled predicate at the action level)', () => {
    for (const id of ['tool_call.copy.name', 'tool_call.copy.input', 'tool_call.copy.id']) {
      const action = TOOL_CALL_ACTIONS.find((a) => a.id === id);
      expect(action?.disabled).toBeUndefined();
    }
  });

  it('copy.output predicate is gated by live call state, not a fixed milestone', () => {
    // Unlike disabled-with-tooltip items, `tool_call.copy.output` has
    // a dynamic predicate that greys out only while the call is still
    // running. Once output or error arrives the row re-enables.
    const action = TOOL_CALL_ACTIONS.find((a) => a.id === 'tool_call.copy.output');
    expect(typeof action?.disabled).toBe('function');
  });
});
