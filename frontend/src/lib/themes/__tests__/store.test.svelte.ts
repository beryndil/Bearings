/**
 * Tests for the theme store — picker mutation, persistence success +
 * failure, cross-tab sync.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  THEME_DATA_ATTR_NAME,
  THEME_DEFAULT,
  THEME_MIDNIGHT_GLASS,
  THEME_PAPER_LIGHT,
  THEME_STORAGE_KEY,
} from "../../config";
import { _resetForTests, setTheme, syncFromStorage, themeStore } from "../store.svelte";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute(THEME_DATA_ATTR_NAME);
  _resetForTests(THEME_MIDNIGHT_GLASS);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("setTheme", () => {
  it("updates store, DOM, and localStorage atomically on success", () => {
    const ok = setTheme(THEME_PAPER_LIGHT);
    expect(ok).toBe(true);
    expect(themeStore.theme).toBe(THEME_PAPER_LIGHT);
    expect(themeStore.lastSaveOk).toBe(true);
    expect(document.documentElement.getAttribute(THEME_DATA_ATTR_NAME)).toBe(THEME_PAPER_LIGHT);
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe(THEME_PAPER_LIGHT);
  });

  it("flips lastSaveOk to false and reverts the DOM on storage failure", () => {
    // Establish a prior persisted choice that the failure path can revert to.
    window.localStorage.setItem(THEME_STORAGE_KEY, THEME_DEFAULT);
    _resetForTests(THEME_DEFAULT);

    const proto = Object.getPrototypeOf(window.localStorage) as { setItem: () => void };
    const original = proto.setItem;
    let calls = 0;
    proto.setItem = function (...args: unknown[]) {
      calls += 1;
      if (calls === 1) {
        throw new Error("quota");
      }
      return original.apply(this, args as never);
    };
    try {
      const ok = setTheme(THEME_PAPER_LIGHT);
      expect(ok).toBe(false);
      expect(themeStore.lastSaveOk).toBe(false);
      expect(themeStore.theme).toBe(THEME_DEFAULT);
      expect(document.documentElement.getAttribute(THEME_DATA_ATTR_NAME)).toBe(THEME_DEFAULT);
    } finally {
      proto.setItem = original;
    }
  });
});

describe("syncFromStorage", () => {
  it("mirrors a persisted change written by another tab", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, THEME_PAPER_LIGHT);
    syncFromStorage();
    expect(themeStore.theme).toBe(THEME_PAPER_LIGHT);
    expect(document.documentElement.getAttribute(THEME_DATA_ATTR_NAME)).toBe(THEME_PAPER_LIGHT);
  });

  it("no-ops when the persisted value matches the current theme", () => {
    _resetForTests(THEME_DEFAULT);
    window.localStorage.setItem(THEME_STORAGE_KEY, THEME_DEFAULT);
    syncFromStorage();
    expect(themeStore.theme).toBe(THEME_DEFAULT);
  });

  it("no-ops when nothing is persisted (e.g. another tab cleared storage)", () => {
    syncFromStorage();
    expect(themeStore.theme).toBe(THEME_MIDNIGHT_GLASS);
  });
});
