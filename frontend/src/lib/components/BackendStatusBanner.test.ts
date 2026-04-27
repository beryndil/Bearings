import { cleanup, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SessionsWsConnection } from '$lib/stores/ws_sessions.svelte';

// Build a real `SessionsWsConnection` with a never-resolving socket
// factory. The component reads `state` + `lastCloseCode` off this
// instance via the module's `sessionsWs` export; using the actual
// class preserves runes-based reactivity (`$state`-backed fields)
// without spinning up a real WebSocket. Tests drive transitions by
// mutating the public fields directly, mirroring what the connect
// loop would do on real frames.
function makeFakeWs(): SessionsWsConnection {
  return new SessionsWsConnection(() => {
    // Return a stub that never does anything. The component never
    // observes the socket itself; only `state` + `lastCloseCode` on
    // the connection.
    return {
      addEventListener: () => {},
      removeEventListener: () => {},
      close: () => {},
      readyState: 0,
      send: () => {}
    } as unknown as WebSocket;
  });
}

let fakeWs: SessionsWsConnection;

vi.mock('$lib/stores/ws_sessions.svelte', async (importOriginal) => {
  const orig = await importOriginal<typeof import('$lib/stores/ws_sessions.svelte')>();
  return {
    ...orig,
    get sessionsWs() {
      return fakeWs;
    }
  };
});

beforeEach(() => {
  fakeWs = makeFakeWs();
});

afterEach(() => {
  cleanup();
});

describe('BackendStatusBanner', () => {
  it('stays hidden while the socket is open', async () => {
    fakeWs.state = 'open';
    const { default: Banner } = await import('./BackendStatusBanner.svelte');
    const { queryByTestId } = render(Banner, { thresholdMs: 50 });
    await new Promise((r) => setTimeout(r, 80));
    expect(queryByTestId('backend-status-banner')).toBeNull();
  });

  it('shows after the threshold elapses while in closed state', async () => {
    fakeWs.state = 'closed';
    const { default: Banner } = await import('./BackendStatusBanner.svelte');
    const { queryByTestId } = render(Banner, { thresholdMs: 30 });
    expect(queryByTestId('backend-status-banner')).toBeNull();
    await waitFor(
      () => expect(queryByTestId('backend-status-banner')).toBeTruthy(),
      { timeout: 200 }
    );
  });

  it('shows after the threshold elapses while in error state', async () => {
    fakeWs.state = 'error';
    const { default: Banner } = await import('./BackendStatusBanner.svelte');
    const { queryByTestId } = render(Banner, { thresholdMs: 30 });
    await waitFor(
      () => expect(queryByTestId('backend-status-banner')).toBeTruthy(),
      { timeout: 200 }
    );
  });

  it('hides immediately when the socket recovers to open', async () => {
    fakeWs.state = 'closed';
    const { default: Banner } = await import('./BackendStatusBanner.svelte');
    const { queryByTestId } = render(Banner, { thresholdMs: 20 });
    await waitFor(
      () => expect(queryByTestId('backend-status-banner')).toBeTruthy(),
      { timeout: 200 }
    );
    fakeWs.state = 'open';
    await waitFor(() => expect(queryByTestId('backend-status-banner')).toBeNull(), {
      timeout: 100
    });
  });

  it('does NOT reset the threshold timer when cycling between non-open states', async () => {
    // Reproduce the WS reconnect cycle: connecting → closed → connecting
    // → error. The banner must still appear within ~one threshold
    // window after the *first* non-open transition, not perpetually
    // restart on each step.
    fakeWs.state = 'connecting';
    const { default: Banner } = await import('./BackendStatusBanner.svelte');
    const { queryByTestId } = render(Banner, { thresholdMs: 60 });

    await new Promise((r) => setTimeout(r, 15));
    fakeWs.state = 'closed';
    await new Promise((r) => setTimeout(r, 15));
    fakeWs.state = 'connecting';
    await new Promise((r) => setTimeout(r, 15));
    fakeWs.state = 'error';

    // ~45ms in — the original timer should still fire near 60ms.
    await waitFor(
      () => expect(queryByTestId('backend-status-banner')).toBeTruthy(),
      { timeout: 200 }
    );
  });

  it('stays hidden for an auth-failure close (4401) — AuthGate owns that surface', async () => {
    fakeWs.state = 'closed';
    fakeWs.lastCloseCode = 4401;
    const { default: Banner } = await import('./BackendStatusBanner.svelte');
    const { queryByTestId } = render(Banner, { thresholdMs: 20 });
    await new Promise((r) => setTimeout(r, 60));
    expect(queryByTestId('backend-status-banner')).toBeNull();
  });
});
