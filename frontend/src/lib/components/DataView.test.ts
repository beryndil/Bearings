import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import DataViewHarness from './DataViewHarness.svelte';

afterEach(cleanup);

// DataView is the §9 Loading / Success / Error / Empty wrapper. The
// harness exposes one "success body" so each test can flip a single
// prop and verify the right branch renders. Branch priority is
// error → loading → empty → success; tests cover that order plus
// the retry-callback wiring.

describe('DataView', () => {
  it('renders the success body when no other state applies', () => {
    const { getByTestId, queryByTestId } = render(DataViewHarness, {
      loading: false,
      error: null,
      isEmpty: false
    });
    expect(getByTestId('dataview-success').textContent).toContain('success body');
    expect(queryByTestId('dataview-loading')).toBeNull();
    expect(queryByTestId('dataview-error')).toBeNull();
    expect(queryByTestId('dataview-empty')).toBeNull();
  });

  it('renders the skeleton loading block when loading=true', () => {
    const { getByTestId, queryByTestId } = render(DataViewHarness, {
      loading: true,
      error: null,
      isEmpty: false,
      loadingLabel: 'Loading sessions'
    });
    const node = getByTestId('dataview-loading');
    expect(node.getAttribute('aria-busy')).toBe('true');
    expect(node.getAttribute('aria-label')).toBe('Loading sessions');
    // Three pulse bars are present (visual + sr-only label).
    expect(node.querySelectorAll('.animate-pulse').length).toBe(3);
    expect(queryByTestId('dataview-success')).toBeNull();
  });

  it('renders the empty branch with the supplied label when isEmpty=true', () => {
    const { getByTestId } = render(DataViewHarness, {
      loading: false,
      error: null,
      isEmpty: true,
      emptyLabel: 'No sessions yet.'
    });
    const empty = getByTestId('dataview-empty');
    expect(empty.textContent?.trim()).toBe('No sessions yet.');
  });

  it('renders the error branch with the message and a working retry button', async () => {
    const onRetry = vi.fn();
    const { getByTestId, queryByTestId } = render(DataViewHarness, {
      loading: false,
      error: 'fetch failed: network unreachable',
      isEmpty: false,
      onRetry
    });
    const errorNode = getByTestId('dataview-error');
    expect(errorNode.getAttribute('role')).toBe('alert');
    expect(errorNode.textContent).toContain('fetch failed: network unreachable');
    const retry = getByTestId('dataview-retry');
    await fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledTimes(1);
    // Loading and success stay hidden while error is showing.
    expect(queryByTestId('dataview-loading')).toBeNull();
    expect(queryByTestId('dataview-success')).toBeNull();
  });

  it('hides the retry button when no onRetry is supplied', () => {
    const { getByTestId, queryByTestId } = render(DataViewHarness, {
      loading: false,
      error: 'something broke',
      isEmpty: false
    });
    expect(getByTestId('dataview-error')).toBeTruthy();
    expect(queryByTestId('dataview-retry')).toBeNull();
  });

  it('error trumps loading when both are set', () => {
    const { getByTestId, queryByTestId } = render(DataViewHarness, {
      loading: true,
      error: 'error wins',
      isEmpty: false
    });
    expect(getByTestId('dataview-error').textContent).toContain('error wins');
    expect(queryByTestId('dataview-loading')).toBeNull();
  });

  it('loading trumps empty when both are set', () => {
    const { getByTestId, queryByTestId } = render(DataViewHarness, {
      loading: true,
      error: null,
      isEmpty: true
    });
    expect(getByTestId('dataview-loading')).toBeTruthy();
    expect(queryByTestId('dataview-empty')).toBeNull();
  });
});
