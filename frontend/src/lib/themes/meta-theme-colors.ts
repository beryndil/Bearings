/**
 * Mobile-browser-chrome `<meta name="theme-color">` value per bundled
 * theme. Single canonical source for runtime code (`preferences.svelte
 * .ts` imports from here).
 *
 * Drift constraint:
 * The no-flash boot script in `app.html` runs synchronously BEFORE
 * any module loads — that's what makes it no-flash — so it can't
 * `import` from this module. It keeps its own inline literal that
 * MUST stay in sync with this table. To make drift loud rather than
 * silent, `preferences.svelte.ts` runs a drift detector after init:
 * if the meta tag's actual content (set by the boot script) doesn't
 * match what we'd compute from this module for the resolved theme,
 * we `console.warn` so an ordinary dev session catches it.
 *
 * Adding a theme:
 *  1. Add the entry here.
 *  2. Add the same entry to the `THEME_COLORS` literal inside
 *     `app.html`'s no-flash boot script.
 *  3. Add the matching CSS rules under
 *     `frontend/src/lib/themes/<theme>.css`.
 *
 * Removing a theme: reverse, in any order.
 */

export const THEME_META_COLORS: Record<string, string> = {
  'midnight-glass': '#0A0E1C',
  'default': '#020617',
  'paper-light': '#FAF7F0'
};

/** Default for first-paint when no theme has been picked yet. Mirrors
 * the OS-color-scheme fallback the boot script uses (light → paper-
 * light, otherwise → midnight-glass). Imported by the runtime store
 * for parity with the boot path. */
export const DEFAULT_THEME = 'midnight-glass';
