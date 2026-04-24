import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { openAgentSocket, openSessionsSocket } from './core';

type WsCall = { url: string; protocols: string | string[] | undefined };

/** Stub the global `WebSocket` to a constructor that just records the
 * args. Returning a minimal shape is fine — nothing here calls back
 * into the socket. */
function stubWebSocket(): WsCall[] {
  const calls: WsCall[] = [];
  class StubWS {
    constructor(url: string, protocols?: string | string[]) {
      calls.push({ url, protocols });
    }
  }
  vi.stubGlobal('WebSocket', StubWS as unknown as typeof WebSocket);
  return calls;
}

beforeEach(() => {
  // jsdom's default location is http://localhost:3000; good enough.
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('openAgentSocket', () => {
  it('passes bearer subprotocols when a token is stored', () => {
    localStorage.setItem('bearings:token', 's3cret');
    const calls = stubWebSocket();

    openAgentSocket('sid-abc', 0);

    expect(calls).toHaveLength(1);
    // Token MUST NOT appear in the URL (audit §1 fix: out of access
    // logs / Referer / browser history).
    expect(calls[0].url).not.toContain('token=');
    expect(calls[0].url).not.toContain('s3cret');
    expect(calls[0].url).toMatch(/\/ws\/sessions\/sid-abc$/);
    expect(calls[0].protocols).toEqual(['bearings.bearer.v1', 'bearer.s3cret']);
  });

  it('passes undefined protocols when no token is set', () => {
    const calls = stubWebSocket();

    openAgentSocket('sid-abc', 0);

    expect(calls[0].protocols).toBeUndefined();
  });

  it('adds since_seq to the query string, never the token', () => {
    localStorage.setItem('bearings:token', 's3cret');
    const calls = stubWebSocket();

    openAgentSocket('sid-abc', 42);

    expect(calls[0].url).toContain('since_seq=42');
    expect(calls[0].url).not.toContain('token=');
    expect(calls[0].protocols).toEqual(['bearings.bearer.v1', 'bearer.s3cret']);
  });
});

describe('openSessionsSocket', () => {
  it('passes bearer subprotocols and leaves the URL clean', () => {
    localStorage.setItem('bearings:token', 'tok-xyz');
    const calls = stubWebSocket();

    openSessionsSocket();

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toMatch(/\/ws\/sessions$/);
    expect(calls[0].url).not.toContain('token=');
    expect(calls[0].protocols).toEqual(['bearings.bearer.v1', 'bearer.tok-xyz']);
  });

  it('omits the subprotocol arg when auth is disabled', () => {
    const calls = stubWebSocket();

    openSessionsSocket();

    expect(calls[0].protocols).toBeUndefined();
  });
});
