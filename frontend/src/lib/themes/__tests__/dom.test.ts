/**
 * Unit tests for the DOM-side theme apply helpers.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  THEME_COLOR_HEX,
  THEME_DATA_ATTR_NAME,
  THEME_DEFAULT,
  THEME_META_NAME,
  THEME_MIDNIGHT_GLASS,
  THEME_PAPER_LIGHT,
} from "../../config";
import { applyThemeColorMeta, applyThemeToDom, readDomTheme } from "../dom";

beforeEach(() => {
  document.documentElement.removeAttribute(THEME_DATA_ATTR_NAME);
  document.querySelectorAll(`meta[name="${THEME_META_NAME}"]`).forEach((m) => m.remove());
});

describe("applyThemeToDom", () => {
  it("writes data-theme to the document root", () => {
    applyThemeToDom(THEME_PAPER_LIGHT);
    expect(document.documentElement.getAttribute(THEME_DATA_ATTR_NAME)).toBe(THEME_PAPER_LIGHT);
  });

  it("creates a missing theme-color meta tag and writes the right hex", () => {
    applyThemeToDom(THEME_DEFAULT);
    const meta = document.querySelector(`meta[name="${THEME_META_NAME}"]`);
    expect(meta).not.toBeNull();
    expect(meta?.getAttribute("content")).toBe(THEME_COLOR_HEX[THEME_DEFAULT]);
  });

  it("updates an existing theme-color meta tag in place", () => {
    const existing = document.createElement("meta");
    existing.setAttribute("name", THEME_META_NAME);
    existing.setAttribute("content", "#000000");
    document.head.appendChild(existing);

    applyThemeToDom(THEME_MIDNIGHT_GLASS);
    expect(existing.getAttribute("content")).toBe(THEME_COLOR_HEX[THEME_MIDNIGHT_GLASS]);
    expect(document.querySelectorAll(`meta[name="${THEME_META_NAME}"]`)).toHaveLength(1);
  });
});

describe("applyThemeColorMeta", () => {
  it("only updates the meta tag, not data-theme", () => {
    applyThemeColorMeta(THEME_PAPER_LIGHT);
    expect(document.documentElement.hasAttribute(THEME_DATA_ATTR_NAME)).toBe(false);
    expect(document.querySelector(`meta[name="${THEME_META_NAME}"]`)?.getAttribute("content")).toBe(
      THEME_COLOR_HEX[THEME_PAPER_LIGHT],
    );
  });
});

describe("readDomTheme", () => {
  it("returns the active data-theme value", () => {
    applyThemeToDom(THEME_DEFAULT);
    expect(readDomTheme()).toBe(THEME_DEFAULT);
  });

  it("returns null when no data-theme is set", () => {
    expect(readDomTheme()).toBe(null);
  });
});
