/**
 * Unit tests for the Phase 5 reorg bridge store.
 *
 * The store is deliberately tiny — one reactive slot plus set / clear.
 * These tests pin the contract the message-action handlers rely on:
 *   - publishing a request replaces any previous one (latest wins),
 *   - `clear()` returns pending to null so Conversation.svelte can
 *     mark a request handled without reopening it on unrelated state
 *     changes.
 */

import { afterEach, describe, expect, it } from 'vitest';

import { reorgStore } from './reorg.svelte';

afterEach(() => {
  reorgStore.clear();
});

describe('reorgStore', () => {
  it('starts with no pending request', () => {
    expect(reorgStore.pending).toBeNull();
  });

  it('publishes a move request verbatim', () => {
    reorgStore.request({ kind: 'move', messageId: 'm-1', sessionId: 's-1' });
    expect(reorgStore.pending).toEqual({
      kind: 'move',
      messageId: 'm-1',
      sessionId: 's-1'
    });
  });

  it('second request replaces the first (latest wins)', () => {
    reorgStore.request({ kind: 'move', messageId: 'm-1', sessionId: 's-1' });
    reorgStore.request({ kind: 'split', messageId: 'm-2', sessionId: 's-1' });
    expect(reorgStore.pending?.kind).toBe('split');
    expect(reorgStore.pending?.messageId).toBe('m-2');
  });

  it('clear returns pending to null', () => {
    reorgStore.request({ kind: 'split', messageId: 'm-9', sessionId: 's-9' });
    reorgStore.clear();
    expect(reorgStore.pending).toBeNull();
  });
});
