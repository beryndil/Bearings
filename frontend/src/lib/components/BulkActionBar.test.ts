import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import BulkActionBar from './BulkActionBar.svelte';

afterEach(cleanup);

describe('BulkActionBar', () => {
  it('shows the selection count and three action buttons', () => {
    const { getByTestId, getByText } = render(BulkActionBar, {
      count: 3,
      onMove: vi.fn(),
      onSplit: vi.fn(),
      onCancel: vi.fn(),
    });
    expect(getByText('3 selected')).toBeInTheDocument();
    expect(getByTestId('bulk-move').textContent).toContain('Move 3');
    expect(getByTestId('bulk-split')).toBeInTheDocument();
    expect(getByTestId('bulk-cancel')).toBeInTheDocument();
  });

  it('disables move + split when the selection is empty', () => {
    const { getByTestId } = render(BulkActionBar, {
      count: 0,
      onMove: vi.fn(),
      onSplit: vi.fn(),
      onCancel: vi.fn(),
    });
    expect(getByTestId('bulk-move')).toBeDisabled();
    expect(getByTestId('bulk-split')).toBeDisabled();
    // Cancel stays live so the user can always exit the mode.
    expect(getByTestId('bulk-cancel')).not.toBeDisabled();
  });

  it('clicking Move / Split / Cancel fires the matching callback', async () => {
    const onMove = vi.fn();
    const onSplit = vi.fn();
    const onCancel = vi.fn();
    const { getByTestId } = render(BulkActionBar, {
      count: 2,
      onMove,
      onSplit,
      onCancel,
    });
    await fireEvent.click(getByTestId('bulk-move'));
    await fireEvent.click(getByTestId('bulk-split'));
    await fireEvent.click(getByTestId('bulk-cancel'));
    expect(onMove).toHaveBeenCalledTimes(1);
    expect(onSplit).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('`m` / `s` shortcuts fire move / split when anything is selected', async () => {
    const onMove = vi.fn();
    const onSplit = vi.fn();
    render(BulkActionBar, {
      count: 1,
      onMove,
      onSplit,
      onCancel: vi.fn(),
    });
    await fireEvent.keyDown(document, { key: 'm' });
    await fireEvent.keyDown(document, { key: 's' });
    expect(onMove).toHaveBeenCalledTimes(1);
    expect(onSplit).toHaveBeenCalledTimes(1);
  });

  it('Escape always fires onCancel', async () => {
    const onCancel = vi.fn();
    render(BulkActionBar, {
      count: 0,
      onMove: vi.fn(),
      onSplit: vi.fn(),
      onCancel,
    });
    await fireEvent.keyDown(document, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('shortcuts are no-ops when count is 0', async () => {
    const onMove = vi.fn();
    const onSplit = vi.fn();
    render(BulkActionBar, {
      count: 0,
      onMove,
      onSplit,
      onCancel: vi.fn(),
    });
    await fireEvent.keyDown(document, { key: 'm' });
    await fireEvent.keyDown(document, { key: 's' });
    expect(onMove).not.toHaveBeenCalled();
    expect(onSplit).not.toHaveBeenCalled();
  });

  it('modifier keys let the browser shortcut through', async () => {
    const onMove = vi.fn();
    const onSplit = vi.fn();
    render(BulkActionBar, {
      count: 2,
      onMove,
      onSplit,
      onCancel: vi.fn(),
    });
    // Cmd+S / Ctrl+M must still hit the browser.
    await fireEvent.keyDown(document, { key: 's', metaKey: true });
    await fireEvent.keyDown(document, { key: 'm', ctrlKey: true });
    expect(onMove).not.toHaveBeenCalled();
    expect(onSplit).not.toHaveBeenCalled();
  });

  it('shortcuts are ignored when an input / textarea owns focus', async () => {
    const onMove = vi.fn();
    render(BulkActionBar, {
      count: 2,
      onMove,
      onSplit: vi.fn(),
      onCancel: vi.fn(),
    });
    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();
    try {
      await fireEvent.keyDown(document, { key: 'm' });
      expect(onMove).not.toHaveBeenCalled();
    } finally {
      input.remove();
    }
  });
});
