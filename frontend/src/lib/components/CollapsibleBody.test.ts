import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CollapsibleBody from './CollapsibleBody.svelte';

afterEach(cleanup);

// scrollHeight is a read-only getter in jsdom. Override on the
// prototype so the component's ResizeObserver-seeded measurement
// reads the value we want. Callers set `currentHeight` before render
// to control the first measurement.
let currentHeight = 0;
const originalDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollHeight');

beforeEach(() => {
  currentHeight = 0;
  Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
    configurable: true,
    get() {
      return currentHeight;
    }
  });
  // Minimal ResizeObserver stub — the component only uses it to
  // re-measure after content mutations. Tests drive height via the
  // prototype override above.
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

afterEach(() => {
  if (originalDescriptor) {
    Object.defineProperty(HTMLElement.prototype, 'scrollHeight', originalDescriptor);
  } else {
    delete (HTMLElement.prototype as unknown as { scrollHeight?: unknown }).scrollHeight;
  }
  vi.unstubAllGlobals();
});

function baseProps(overrides: Record<string, unknown> = {}) {
  return {
    messageId: 'm-1',
    content: 'body text',
    highlightQuery: '',
    ...overrides
  };
}

describe('CollapsibleBody', () => {
  it('does not fold or show toggle when content is under threshold', async () => {
    currentHeight = 200;
    const { findByTestId, queryByTestId } = render(
      CollapsibleBody,
      baseProps({ thresholdPx: 500 })
    );
    const inner = await findByTestId('collapsible-inner');
    expect(inner.getAttribute('data-folded')).toBe('false');
    expect(queryByTestId('collapse-toggle')).toBeNull();
  });

  it('folds and shows toggle when content exceeds threshold', async () => {
    currentHeight = 900;
    const { findByTestId } = render(CollapsibleBody, baseProps({ thresholdPx: 500 }));
    const inner = await findByTestId('collapsible-inner');
    expect(inner.getAttribute('data-folded')).toBe('true');
    const toggle = await findByTestId('collapse-toggle');
    expect(toggle.textContent?.toLowerCase()).toContain('show full');
  });

  it('toggle expands the body and flips label on click', async () => {
    currentHeight = 900;
    const { findByTestId } = render(CollapsibleBody, baseProps({ thresholdPx: 500 }));
    const toggle = await findByTestId('collapse-toggle');
    await fireEvent.click(toggle);
    const inner = await findByTestId('collapsible-inner');
    expect(inner.getAttribute('data-folded')).toBe('false');
    expect(toggle.textContent?.toLowerCase()).toContain('collapse');
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
  });

  it('persists expanded state to localStorage under the message id', async () => {
    currentHeight = 900;
    const { findByTestId } = render(
      CollapsibleBody,
      baseProps({ messageId: 'persist-me', thresholdPx: 500 })
    );
    const toggle = await findByTestId('collapse-toggle');
    await fireEvent.click(toggle);
    expect(localStorage.getItem('bearings:msg:expanded:persist-me')).toBe('1');
    // Collapsing again clears the key so the default (folded) holds
    // on reload for messages that haven't been deliberately expanded.
    await fireEvent.click(toggle);
    expect(localStorage.getItem('bearings:msg:expanded:persist-me')).toBeNull();
  });

  it('hydrates expanded state from localStorage on mount', async () => {
    currentHeight = 900;
    localStorage.setItem('bearings:msg:expanded:remembered', '1');
    const { findByTestId } = render(
      CollapsibleBody,
      baseProps({ messageId: 'remembered', thresholdPx: 500 })
    );
    const inner = await findByTestId('collapsible-inner');
    expect(inner.getAttribute('data-folded')).toBe('false');
    const toggle = await findByTestId('collapse-toggle');
    expect(toggle.textContent?.toLowerCase()).toContain('collapse');
  });

  it('disabled skips fold even when content is long', async () => {
    currentHeight = 2000;
    const { findByTestId, queryByTestId } = render(
      CollapsibleBody,
      baseProps({ thresholdPx: 500, disabled: true })
    );
    const inner = await findByTestId('collapsible-inner');
    expect(inner.getAttribute('data-folded')).toBe('false');
    expect(queryByTestId('collapse-toggle')).toBeNull();
  });

  it('null messageId still folds and toggles but writes no storage key', async () => {
    currentHeight = 900;
    const setSpy = vi.spyOn(localStorage, 'setItem');
    const { findByTestId } = render(
      CollapsibleBody,
      baseProps({ messageId: null, thresholdPx: 500 })
    );
    const toggle = await findByTestId('collapse-toggle');
    await fireEvent.click(toggle);
    const inner = await findByTestId('collapsible-inner');
    expect(inner.getAttribute('data-folded')).toBe('false');
    expect(setSpy).not.toHaveBeenCalled();
    setSpy.mockRestore();
  });
});
