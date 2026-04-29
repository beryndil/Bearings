/**
 * DOM-side theme application — write the chosen theme onto the
 * document root and the ``<meta name="theme-color">`` tag.
 *
 * Pure functions over the DOM so they are reachable from boot scripts
 * (run before the runtime store materializes) and from the runtime
 * store's mutation path. The store does not own DOM access — it
 * delegates here so a test can assert the apply path without spinning
 * up the full provider component.
 *
 * Behavior anchors:
 *
 * - ``docs/behavior/themes.md`` §"What gets re-themed live" — every
 *   visible surface re-tints synchronously when ``data-theme`` flips.
 * - §"What does NOT get re-themed live" — the mobile-chrome color is
 *   the only piece tracked through the meta-tag write below.
 */
import { THEME_COLOR_HEX, THEME_DATA_ATTR_NAME, THEME_META_NAME, type ThemeId } from "../config";

/**
 * Apply a theme to the document root + the mobile-chrome meta tag.
 * No-ops on non-DOM environments (SSR / vitest before jsdom mounts).
 */
export function applyThemeToDom(theme: ThemeId): void {
  if (typeof document === "undefined") {
    return;
  }
  document.documentElement.setAttribute(THEME_DATA_ATTR_NAME, theme);
  applyThemeColorMeta(theme);
}

/**
 * Update the ``<meta name="theme-color">`` tag — the no-flash boot
 * script paints this on cold load; the runtime corrects any drift on
 * the next tick per ``docs/behavior/themes.md`` §"What gets re-themed
 * live" (the single-frame mismatch caveat).
 *
 * Idempotent: if the tag is missing the function inserts one, so a
 * future static-build that drops the meta tag still ends up with the
 * right address-bar color after the runtime initializes.
 */
export function applyThemeColorMeta(theme: ThemeId): void {
  if (typeof document === "undefined") {
    return;
  }
  let meta = document.querySelector(`meta[name="${THEME_META_NAME}"]`);
  if (meta === null) {
    meta = document.createElement("meta");
    meta.setAttribute("name", THEME_META_NAME);
    document.head.appendChild(meta);
  }
  meta.setAttribute("content", THEME_COLOR_HEX[theme]);
}

/**
 * Read the current ``data-theme`` attribute. Used by tests to verify a
 * boot script ran before the runtime store ticked. Returns ``null`` on
 * non-DOM environments.
 */
export function readDomTheme(): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  return document.documentElement.getAttribute(THEME_DATA_ATTR_NAME);
}
