/**
 * Component test for ``ThemePicker`` — dropdown lists every theme,
 * selection commits immediately + re-tints the DOM, caption matches
 * the doc.
 */
import { fireEvent, render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  KNOWN_THEMES,
  THEME_DATA_ATTR_NAME,
  THEME_MIDNIGHT_GLASS,
  THEME_PAPER_LIGHT,
  THEME_STORAGE_KEY,
  THEME_STRINGS,
} from "../../config";
import ThemePicker from "../ThemePicker.svelte";
import { _resetForTests } from "../store.svelte";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute(THEME_DATA_ATTR_NAME);
  _resetForTests(THEME_MIDNIGHT_GLASS);
});

afterEach(() => {
  document.documentElement.removeAttribute(THEME_DATA_ATTR_NAME);
});

describe("ThemePicker", () => {
  it("renders the caption verbatim from the doc", () => {
    const { getByTestId } = render(ThemePicker);
    expect(getByTestId("theme-picker-caption")).toHaveTextContent(THEME_STRINGS.pickerCaption);
  });

  it("renders one option per theme in the v1 alphabet", () => {
    const { getByTestId } = render(ThemePicker);
    const options = (getByTestId("theme-picker-select") as HTMLSelectElement).options;
    expect(options.length).toBe(KNOWN_THEMES.length);
    for (let i = 0; i < KNOWN_THEMES.length; i += 1) {
      expect(options[i].value).toBe(KNOWN_THEMES[i]);
    }
  });

  it("selecting an option commits the change immediately (live re-theme)", async () => {
    const { getByTestId } = render(ThemePicker);
    const select = getByTestId("theme-picker-select") as HTMLSelectElement;
    await fireEvent.change(select, { target: { value: THEME_PAPER_LIGHT } });
    expect(document.documentElement.getAttribute(THEME_DATA_ATTR_NAME)).toBe(THEME_PAPER_LIGHT);
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe(THEME_PAPER_LIGHT);
  });
});
