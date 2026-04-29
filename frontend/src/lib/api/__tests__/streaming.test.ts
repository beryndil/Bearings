/**
 * Tests for :func:`parseStreamFrame` — covers the two frame kinds
 * plus malformed input.
 */
import { describe, expect, it } from "vitest";

import { parseStreamFrame } from "../streaming";
import { WS_FRAME_KIND_EVENT, WS_FRAME_KIND_HEARTBEAT } from "../../config";

describe("parseStreamFrame — event frames", () => {
  it("parses a token event frame", () => {
    const text = JSON.stringify({
      kind: "event",
      seq: 7,
      event: { session_id: "s", type: "token", message_id: "m", delta: "hi" },
    });
    const frame = parseStreamFrame(text);
    expect(frame).not.toBeNull();
    if (frame === null || frame.kind !== WS_FRAME_KIND_EVENT) {
      throw new Error("expected event frame");
    }
    expect(frame.seq).toBe(7);
    expect(frame.event.type).toBe("token");
  });

  it("rejects negative seq", () => {
    const text = JSON.stringify({
      kind: "event",
      seq: -1,
      event: { session_id: "s", type: "token", message_id: "m", delta: "hi" },
    });
    expect(parseStreamFrame(text)).toBeNull();
  });

  it("rejects an event frame missing the inner type discriminator", () => {
    const text = JSON.stringify({ kind: "event", seq: 0, event: { session_id: "s" } });
    expect(parseStreamFrame(text)).toBeNull();
  });
});

describe("parseStreamFrame — heartbeat frames", () => {
  it("parses a heartbeat frame", () => {
    const text = JSON.stringify({ kind: "heartbeat", ts: 1234.5 });
    const frame = parseStreamFrame(text);
    expect(frame).not.toBeNull();
    if (frame === null || frame.kind !== WS_FRAME_KIND_HEARTBEAT) {
      throw new Error("expected heartbeat frame");
    }
    expect(frame.ts).toBe(1234.5);
  });

  it("rejects a heartbeat without ts", () => {
    expect(parseStreamFrame(JSON.stringify({ kind: "heartbeat" }))).toBeNull();
  });
});

describe("parseStreamFrame — malformed input", () => {
  it("returns null on non-JSON", () => {
    expect(parseStreamFrame("not json")).toBeNull();
  });

  it("returns null on a JSON array (must be object)", () => {
    expect(parseStreamFrame("[1, 2, 3]")).toBeNull();
  });

  it("returns null on an unknown kind", () => {
    expect(parseStreamFrame(JSON.stringify({ kind: "unknown", x: 1 }))).toBeNull();
  });
});
