/**
 * Tests for :mod:`stores/composerBridge.svelte.ts` — the small bridge
 * the vault pane writes paste-into-composer requests into. The
 * conversation composer (post-2.3) reads from the same store.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  _resetForTests,
  composerBridgeStore,
  consumePendingPaste,
  pasteIntoComposer,
} from "../composerBridge.svelte";

beforeEach(() => {
  _resetForTests();
});

describe("composer bridge", () => {
  it("queues a paste and exposes it on the store", () => {
    pasteIntoComposer({ sessionId: "sess_a", text: "hello", kind: "link" });
    expect(composerBridgeStore.pending).toEqual({
      sessionId: "sess_a",
      text: "hello",
      kind: "link",
    });
  });

  it("consumePendingPaste returns and clears the pending slot", () => {
    pasteIntoComposer({ sessionId: "sess_a", text: "x", kind: "body" });
    const consumed = consumePendingPaste();
    expect(consumed?.sessionId).toBe("sess_a");
    expect(composerBridgeStore.pending).toBeNull();
  });

  it("a second paste replaces the first when not yet consumed", () => {
    pasteIntoComposer({ sessionId: "sess_a", text: "first", kind: "link" });
    pasteIntoComposer({ sessionId: "sess_b", text: "second", kind: "body" });
    expect(composerBridgeStore.pending?.text).toBe("second");
    expect(composerBridgeStore.pending?.sessionId).toBe("sess_b");
  });

  it("consumePendingPaste returns null when no paste is queued", () => {
    expect(consumePendingPaste()).toBeNull();
  });
});
