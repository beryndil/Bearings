import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Message } from '$lib/api';
import MessageTurn from './MessageTurn.svelte';

afterEach(cleanup);

function msg(overrides: Partial<Message> = {}): Message {
  return {
    id: 'm-1',
    session_id: 's-1',
    role: 'user',
    content: 'hello',
    thinking: null,
    created_at: '2026-04-21T00:00:00+00:00',
    ...overrides
  };
}

type Render = Record<string, unknown>;

function baseProps(overrides: Render = {}): Render {
  return {
    user: msg({ id: 'u-1', role: 'user', content: 'user text' }),
    assistant: msg({ id: 'a-1', role: 'assistant', content: 'assistant text' }),
    thinking: '',
    toolCalls: [],
    streamingContent: '',
    streamingThinking: '',
    isStreaming: false,
    highlightQuery: '',
    copiedMsgId: null,
    onCopyMessage: vi.fn(),
    ...overrides
  };
}

describe('MessageTurn (bulk mode)', () => {
  it('renders the ⋯ menu and no checkbox when bulkMode is off', () => {
    const { queryAllByTestId } = render(
      MessageTurn,
      baseProps({
        onMoveMessage: vi.fn(),
        onSplitAfter: vi.fn()
      })
    );
    expect(queryAllByTestId('message-menu-trigger').length).toBeGreaterThan(0);
    expect(queryAllByTestId('bulk-checkbox')).toHaveLength(0);
  });

  it('hides the ⋯ menu and renders checkboxes when bulkMode is on', () => {
    const { queryAllByTestId, getAllByTestId } = render(
      MessageTurn,
      baseProps({
        onMoveMessage: vi.fn(),
        onSplitAfter: vi.fn(),
        bulkMode: true,
        selectedIds: new Set<string>(),
        onToggleSelect: vi.fn()
      })
    );
    expect(queryAllByTestId('message-menu-trigger')).toHaveLength(0);
    const boxes = getAllByTestId('bulk-checkbox');
    expect(boxes).toHaveLength(2);
    expect(boxes.map((b) => b.getAttribute('data-message-id'))).toEqual(['u-1', 'a-1']);
  });

  it('clicking a checkbox fires onToggleSelect with the message and shiftKey flag', async () => {
    const onToggleSelect = vi.fn();
    const { getAllByTestId } = render(
      MessageTurn,
      baseProps({
        bulkMode: true,
        selectedIds: new Set<string>(),
        onToggleSelect
      })
    );
    const boxes = getAllByTestId('bulk-checkbox');
    await fireEvent.click(boxes[0], { shiftKey: false });
    await fireEvent.click(boxes[1], { shiftKey: true });
    expect(onToggleSelect).toHaveBeenCalledTimes(2);
    expect(onToggleSelect.mock.calls[0][0].id).toBe('u-1');
    expect(onToggleSelect.mock.calls[0][1]).toBe(false);
    expect(onToggleSelect.mock.calls[1][0].id).toBe('a-1');
    expect(onToggleSelect.mock.calls[1][1]).toBe(true);
  });

  it('selected rows get an emerald highlight border', () => {
    const selected = new Set(['u-1']);
    const { getByTestId } = render(
      MessageTurn,
      baseProps({
        bulkMode: true,
        selectedIds: selected,
        onToggleSelect: vi.fn()
      })
    );
    const userArticle = getByTestId('user-article');
    expect(userArticle.className).toMatch(/border-emerald-500/);
    const assistantArticle = getByTestId('assistant-article');
    expect(assistantArticle.className).not.toMatch(/border-emerald-500/);
  });

  it('checkbox check state reflects selectedIds membership', () => {
    const selected = new Set(['a-1']);
    const { getAllByTestId } = render(
      MessageTurn,
      baseProps({
        bulkMode: true,
        selectedIds: selected,
        onToggleSelect: vi.fn()
      })
    );
    const boxes = getAllByTestId('bulk-checkbox') as HTMLInputElement[];
    // u-1 unchecked, a-1 checked
    expect(boxes[0].checked).toBe(false);
    expect(boxes[1].checked).toBe(true);
  });
});
