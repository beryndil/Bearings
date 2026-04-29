/**
 * Component test for ``ThemeProvider`` — applies the boot-resolved
 * theme on mount + surfaces the save-failed toast when the store flags
 * a persistence failure.
 */
import { fireEvent, render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  THEME_DATA_ATTR_NAME,
  THEME_DEFAULT,
  THEME_MIDNIGHT_GLASS,
  THEME_PAPER_LIGHT,
  THEME_STORAGE_KEY,
  THEME_STRINGS,
} from "../../config";
import ThemeProvider from "../ThemeProvider.svelte";
import { _resetForTests, setTheme } from "../store.svelte";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute(THEME_DATA_ATTR_NAME);
  _resetForTests(THEME_MIDNIGHT_GLASS);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ThemeProvider", () => {
  it("applies the store theme to the DOM on mount", () => {
    _resetForTests(THEME_DEFAULT);
    render(ThemeProvider);
    expect(document.documentElement.getAttribute(THEME_DATA_ATTR_NAME)).toBe(THEME_DEFAULT);
  });

  it("renders the save-failed toast after a setTheme failure", async () => {
    const { findByTestId } = render(ThemeProvider);
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
    setTheme(THEME_PAPER_LIGHT);
    const toast = await findByTestId("theme-provider-save-failed-toast");
    expect(toast).toHaveTextContent(THEME_STRINGS.saveFailedToast);
  });

  it("dismiss button hides the save-failed toast", async () => {
    const { findByTestId, queryByTestId } = render(ThemeProvider);
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
    setTheme(THEME_PAPER_LIGHT);
    const dismiss = await findByTestId("theme-provider-save-failed-toast-dismiss");
    await fireEvent.click(dismiss);
    expect(queryByTestId("theme-provider-save-failed-toast")).toBeNull();
  });

  it("syncs to a storage event from another tab", () => {
    render(ThemeProvider);
    window.localStorage.setItem(THEME_STORAGE_KEY, THEME_PAPER_LIGHT);
    window.dispatchEvent(
      new StorageEvent("storage", { key: THEME_STORAGE_KEY, newValue: THEME_PAPER_LIGHT }),
    );
    expect(document.documentElement.getAttribute(THEME_DATA_ATTR_NAME)).toBe(THEME_PAPER_LIGHT);
  });
});
