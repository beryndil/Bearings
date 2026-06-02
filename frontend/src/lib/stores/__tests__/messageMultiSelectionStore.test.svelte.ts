/**
 * Unit tests for :mod:`stores/messageMultiSelectionStore.svelte.ts`.
 *
 * Verifies the toggleMessageId, clearMessageSelection, and
 * _resetMessageSelectionForTests helpers against the reactive state.
 */
import { describe, expect, it, afterEach } from "vitest";
import {
  messageMultiSelectionStore,
  toggleMessageId,
  clearMessageSelection,
  _resetMessageSelectionForTests,
} from "../messageMultiSelectionStore.svelte";

afterEach(() => {
  _resetMessageSelectionForTests();
});

describe("messageMultiSelectionStore", () => {
  it("starts empty", () => {
    expect(messageMultiSelectionStore.ids.size).toBe(0);
  });

  it("toggleMessageId adds a new id", () => {
    toggleMessageId("msg_a");
    expect(messageMultiSelectionStore.ids.has("msg_a")).toBe(true);
    expect(messageMultiSelectionStore.ids.size).toBe(1);
  });

  it("toggleMessageId removes an existing id", () => {
    toggleMessageId("msg_a");
    toggleMessageId("msg_a");
    expect(messageMultiSelectionStore.ids.size).toBe(0);
  });

  it("toggleMessageId handles multiple distinct ids", () => {
    toggleMessageId("msg_a");
    toggleMessageId("msg_b");
    expect(messageMultiSelectionStore.ids.has("msg_a")).toBe(true);
    expect(messageMultiSelectionStore.ids.has("msg_b")).toBe(true);
    expect(messageMultiSelectionStore.ids.size).toBe(2);
  });

  it("clearMessageSelection empties the set", () => {
    toggleMessageId("msg_a");
    toggleMessageId("msg_b");
    clearMessageSelection();
    expect(messageMultiSelectionStore.ids.size).toBe(0);
  });

  it("clearMessageSelection is a no-op when already empty", () => {
    // Should not throw.
    clearMessageSelection();
    expect(messageMultiSelectionStore.ids.size).toBe(0);
  });

  it("_resetMessageSelectionForTests empties the set", () => {
    toggleMessageId("msg_x");
    _resetMessageSelectionForTests();
    expect(messageMultiSelectionStore.ids.size).toBe(0);
  });
});
