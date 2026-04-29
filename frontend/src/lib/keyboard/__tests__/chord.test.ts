/**
 * Chord matching + serialization tests.
 */
import { describe, expect, it } from "vitest";

import { chordDisplayString, chordKey, eventToCodeKey, eventToNamedKey } from "../chord";

describe("chordKey", () => {
  it("encodes a bare letter chord by physical code", () => {
    expect(chordKey({ code: "KeyC" })).toBe("code:KeyC");
  });

  it("orders modifiers ctrl → shift → alt deterministically", () => {
    expect(chordKey({ code: "KeyP", ctrl: true, shift: true, alt: true })).toBe(
      "ctrl+shift+alt+code:KeyP",
    );
  });

  it("encodes a named-key chord by produced character", () => {
    expect(chordKey({ key: "?" })).toBe("key:?");
  });

  it("includes shift on a named-key chord when set", () => {
    expect(chordKey({ key: "?", shift: true })).toBe("shift+key:?");
  });
});

describe("event normalization", () => {
  it("treats Cmd as Ctrl on Mac (modifier-equivalence)", () => {
    const event = new KeyboardEvent("keydown", { code: "KeyP", metaKey: true, shiftKey: true });
    expect(eventToCodeKey(event)).toBe("ctrl+shift+code:KeyP");
  });

  it("normalizes a bare ?keystroke to the named-key with shift on US-style layouts", () => {
    const event = new KeyboardEvent("keydown", { key: "?", shiftKey: true });
    expect(eventToNamedKey(event)).toBe("shift+key:?");
  });

  it("normalizes a bare Esc keystroke to a non-modifier named-key", () => {
    const event = new KeyboardEvent("keydown", { key: "Escape" });
    expect(eventToNamedKey(event)).toBe("key:Escape");
  });
});

describe("chordDisplayString", () => {
  it("joins display capsules with +", () => {
    expect(chordDisplayString({ code: "KeyC", shift: true, display: ["Shift", "C"] })).toBe(
      "Shift+C",
    );
  });
});
