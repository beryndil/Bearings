import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ReorgUndoToast from './ReorgUndoToast.svelte';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.useFakeTimers();
});

describe('ReorgUndoToast', () => {
  it('renders the message and a countdown button', () => {
    const { getByText, getByTestId } = render(ReorgUndoToast, {
      message: 'Moved 1 message to "Beta".',
      onUndo: vi.fn(),
      onDismiss: vi.fn()
    });
    expect(getByText('Moved 1 message to "Beta".')).toBeInTheDocument();
    // Initial countdown shows 30s (default window).
    expect(getByTestId('reorg-undo-button').textContent).toMatch(/Undo \(30s\)/);
  });

  it('auto-dismisses when the window elapses', async () => {
    const onDismiss = vi.fn();
    render(ReorgUndoToast, {
      message: 'done',
      windowMs: 1000,
      onUndo: vi.fn(),
      onDismiss
    });
    // Advance past the window — the 250ms interval catches zero.
    await vi.advanceTimersByTimeAsync(1500);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('Undo click runs the inverse op then dismisses', async () => {
    const onUndo = vi.fn(async () => {});
    const onDismiss = vi.fn();
    const { getByTestId } = render(ReorgUndoToast, {
      message: 'done',
      windowMs: 30_000,
      onUndo,
      onDismiss
    });
    await fireEvent.click(getByTestId('reorg-undo-button'));
    await waitFor(() => {
      expect(onUndo).toHaveBeenCalledTimes(1);
      expect(onDismiss).toHaveBeenCalledTimes(1);
    });
  });

  it('Undo button disables while the inverse op is in flight', async () => {
    let resolve!: () => void;
    const pending = new Promise<void>((r) => {
      resolve = r;
    });
    const onUndo = vi.fn(() => pending);
    const { getByTestId } = render(ReorgUndoToast, {
      message: 'done',
      onUndo,
      onDismiss: vi.fn()
    });
    const btn = getByTestId('reorg-undo-button');
    await fireEvent.click(btn);
    expect(btn).toBeDisabled();
    expect(btn.textContent).toContain('Undoing…');
    resolve();
    // Cleanup: let the microtask complete.
    await vi.advanceTimersByTimeAsync(0);
  });

  it('auto-dismiss does not fire after the user clicks Undo', async () => {
    const onUndo = vi.fn(async () => {});
    const onDismiss = vi.fn();
    const { getByTestId } = render(ReorgUndoToast, {
      message: 'done',
      windowMs: 500,
      onUndo,
      onDismiss
    });
    await fireEvent.click(getByTestId('reorg-undo-button'));
    await waitFor(() => expect(onDismiss).toHaveBeenCalledTimes(1));
    // Advance well past the original window — dismiss should stay at 1.
    await vi.advanceTimersByTimeAsync(2000);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
