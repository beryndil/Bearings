/**
 * L4.3.2 — ReplyActionPreview component test.
 *
 * The modal is store-driven: visibility, body content, and footer
 * state all derive from `replyActions.state`. We exercise the modal
 * by mutating the store directly (no fake event source needed) and
 * assert on the rendered DOM. Covers:
 *
 *   - hidden when status='idle'
 *   - opens with the action label + spinner copy when status='streaming'
 *   - body shows accumulated `text` + streaming caret while streaming
 *   - shows cost label after `complete`
 *   - shows error message in red when status='error'
 *   - Copy button writes the text to clipboard
 *   - Send-to-composer dispatches `bearings:composer-prefill` and
 *     closes the modal
 *   - Close / ESC tear down the modal
 */
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { replyActions } from '$lib/stores/replyActions.svelte';
import ReplyActionPreview from './ReplyActionPreview.svelte';

afterEach(() => {
  cleanup();
  replyActions.close();
});

beforeEach(() => {
  // Each test starts with a fresh idle store.
  replyActions.close();
});

function setStreaming(text = ''): void {
  // Drive the store into streaming state without touching the SSE
  // pipeline. Tests bypass `start()` because that opens a real
  // network call.
  replyActions.state = {
    status: 'streaming',
    action: 'summarize',
    label: 'TL;DR',
    messageId: 'm1',
    sessionId: 's1',
    text,
    costUsd: null,
    errorMessage: ''
  };
}

describe('ReplyActionPreview', () => {
  it('is not rendered while the store is idle', () => {
    const { queryByTestId } = render(ReplyActionPreview);
    expect(queryByTestId('reply-action-modal')).toBeNull();
  });

  it('opens with the catalog label when streaming starts', async () => {
    const { getByTestId, queryByTestId } = render(ReplyActionPreview);
    setStreaming();
    await waitFor(() =>
      expect(queryByTestId('reply-action-modal')).not.toBeNull()
    );
    expect(getByTestId('reply-action-label').textContent?.trim()).toBe('TL;DR');
  });

  it('renders streamed text with a blinking caret', async () => {
    const { getByTestId, queryByTestId } = render(ReplyActionPreview);
    setStreaming('alpha beta');
    await waitFor(() =>
      expect(queryByTestId('reply-action-modal')).not.toBeNull()
    );
    const body = getByTestId('reply-action-body');
    expect(body.textContent).toContain('alpha beta');
    // Streaming caret is the `▍` glyph rendered while status is
    // 'streaming'.
    expect(body.textContent).toContain('▍');
  });

  it('shows the cost label and disables the streaming caret on complete', async () => {
    const { getByTestId, queryByTestId } = render(ReplyActionPreview);
    setStreaming('alpha');
    replyActions.state = {
      ...replyActions.state,
      status: 'complete',
      text: 'alpha beta',
      costUsd: 0.0123
    };
    await waitFor(() =>
      expect(queryByTestId('reply-action-modal')).not.toBeNull()
    );
    const body = getByTestId('reply-action-body');
    expect(body.textContent).toContain('alpha beta');
    expect(body.textContent).not.toContain('▍');
    // Header shows formatted cost with 4 decimals.
    expect(getByTestId('reply-action-modal').textContent).toContain('$0.0123');
  });

  it('renders the error message when status=error', async () => {
    const { getByTestId, queryByTestId } = render(ReplyActionPreview);
    replyActions.state = {
      status: 'error',
      action: 'summarize',
      label: 'TL;DR',
      messageId: 'm1',
      sessionId: 's1',
      text: '',
      costUsd: null,
      errorMessage: 'model unavailable'
    };
    await waitFor(() =>
      expect(queryByTestId('reply-action-modal')).not.toBeNull()
    );
    expect(getByTestId('reply-action-body').textContent).toContain(
      'model unavailable'
    );
  });

  it('Copy writes the body text to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText }
    });
    const { getByTestId, queryByTestId } = render(ReplyActionPreview);
    setStreaming('summary body');
    replyActions.state = {
      ...replyActions.state,
      status: 'complete',
      text: 'summary body'
    };
    await waitFor(() =>
      expect(queryByTestId('reply-action-modal')).not.toBeNull()
    );
    await fireEvent.click(getByTestId('reply-action-copy'));
    expect(writeText).toHaveBeenCalledWith('summary body');
  });

  it('Send-to-composer dispatches composer-prefill and closes', async () => {
    const handler = vi.fn();
    window.addEventListener('bearings:composer-prefill', handler);
    try {
      const { getByTestId, queryByTestId } = render(ReplyActionPreview);
      setStreaming('preview text');
      replyActions.state = {
        ...replyActions.state,
        status: 'complete',
        text: 'preview text'
      };
      await waitFor(() =>
        expect(queryByTestId('reply-action-modal')).not.toBeNull()
      );
      await fireEvent.click(getByTestId('reply-action-send'));
      expect(handler).toHaveBeenCalledTimes(1);
      const ev = handler.mock.calls[0][0] as CustomEvent;
      expect(ev.detail).toEqual({ sessionId: 's1', text: 'preview text' });
      // Modal closed → store back to idle.
      expect(replyActions.state.status).toBe('idle');
    } finally {
      window.removeEventListener('bearings:composer-prefill', handler);
    }
  });

  it('Send-to-composer is disabled while streaming', async () => {
    const { getByTestId, queryByTestId } = render(ReplyActionPreview);
    setStreaming('partial');
    await waitFor(() =>
      expect(queryByTestId('reply-action-modal')).not.toBeNull()
    );
    expect(getByTestId('reply-action-send')).toBeDisabled();
  });

  it('Close button cancels the stream and resets store state', async () => {
    const { getByTestId, queryByTestId } = render(ReplyActionPreview);
    setStreaming('partial');
    await waitFor(() =>
      expect(queryByTestId('reply-action-modal')).not.toBeNull()
    );
    // While streaming, the Close button is labelled "Cancel".
    const close = getByTestId('reply-action-close');
    expect(close.textContent?.trim()).toBe('Cancel');
    await fireEvent.click(close);
    expect(replyActions.state.status).toBe('idle');
  });

  it('ESC closes the modal', async () => {
    const { queryByTestId } = render(ReplyActionPreview);
    setStreaming('partial');
    await waitFor(() =>
      expect(queryByTestId('reply-action-modal')).not.toBeNull()
    );
    await fireEvent.keyDown(window, { key: 'Escape' });
    expect(replyActions.state.status).toBe('idle');
  });
});
