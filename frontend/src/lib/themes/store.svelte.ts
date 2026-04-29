/**
 * Theme store — single canonical Svelte 5 store for the active theme.
 *
 * Per arch §1.2 + §2.2 the theme is one canonical store, one file.
 * Components subscribe by reading ``themeStore.theme`` directly inside
 * a ``$derived`` / template expression; mutation flows through
 * :func:`setTheme` so the persistence + DOM-apply path stays in one
 * place.
 *
 * Behavior anchors:
 *
 * - ``docs/behavior/themes.md`` §"Theme picker UI" — selecting an
 *   option commits immediately (no Save button, no debounce).
 * - §"What gets re-themed live" — the change lands synchronously in
 *   the same tick as the persistence success.
 * - §"Failure modes" — a write failure surfaces a toast and reverts
 *   the preview; the active theme remains the previously-saved one.
 */
import { type ThemeId } from "../config";
import { applyThemeToDom } from "./dom";
import { loadStoredTheme, resolveBootTheme, saveStoredTheme } from "./persistence";

interface ThemeState {
  /**
   * Currently-active theme id. Always one of :data:`KNOWN_THEMES`.
   * The boot-time value is the persisted choice if present, else the
   * OS-color-scheme fallback per :func:`resolveBootTheme`.
   */
  theme: ThemeId;
  /**
   * Last persistence-attempt status. ``null`` while no attempt has
   * happened; ``true`` after a successful write; ``false`` after a
   * failed write. The provider component reads this to flash the
   * "couldn't save your theme" toast on ``false``.
   */
  lastSaveOk: boolean | null;
}

const state: ThemeState = $state({
  theme: resolveBootTheme(),
  lastSaveOk: null,
});

/**
 * Reactive proxy. Read ``themeStore.theme`` for the active theme;
 * mutation is :func:`setTheme` — direct writes bypass the persistence
 * + DOM-apply hooks below.
 */
export const themeStore = state;

/**
 * Switch to a new theme. The order is:
 *
 * 1. Apply to the DOM synchronously (no flash; the doc requires the
 *    re-tint to land in the same tick).
 * 2. Persist to localStorage.
 * 3. Update the store's ``theme`` field so subscribers re-render.
 * 4. Update the store's ``lastSaveOk`` field — ``true`` on success,
 *    ``false`` on failure. The provider's ``$effect`` watches this and
 *    surfaces the toast.
 *
 * On persistence failure the store's ``theme`` field is rolled back to
 * whatever ``loadStoredTheme()`` reports (the previously-saved choice;
 * ``null`` reverts to the OS fallback). The DOM is re-applied so the
 * preview matches the rolled-back active theme — i.e. the user does
 * not see a stale color palette while reading the toast.
 */
export function setTheme(next: ThemeId): boolean {
  applyThemeToDom(next);
  const ok = saveStoredTheme(next);
  if (ok) {
    state.theme = next;
    state.lastSaveOk = true;
    return true;
  }
  // Failure path: revert to the previously-saved value (or OS fallback).
  const fallback = loadStoredTheme() ?? state.theme;
  applyThemeToDom(fallback);
  state.theme = fallback;
  state.lastSaveOk = false;
  return false;
}

/**
 * Sync the in-memory theme to the persisted value. Called by the
 * provider's ``storage`` event listener — when another tab writes a
 * new theme, this tab reads the change and mirrors it without
 * triggering a fresh save (a save would feedback-loop the storage
 * event back to the writing tab).
 */
export function syncFromStorage(): void {
  const persisted = loadStoredTheme();
  if (persisted === null || persisted === state.theme) {
    return;
  }
  applyThemeToDom(persisted);
  state.theme = persisted;
}

/**
 * Acknowledge that the provider has surfaced the most-recent
 * save-failed toast (or success, ignored downstream). Resets
 * ``lastSaveOk`` so a subsequent identical setTheme call re-fires the
 * toast effect rather than being collapsed by Svelte's
 * change-detection on an unchanged value.
 */
export function acknowledgeSaveStatus(): void {
  state.lastSaveOk = null;
}

/** Test seam — restore the boot state without re-importing the module. */
export function _resetForTests(theme: ThemeId): void {
  state.theme = theme;
  state.lastSaveOk = null;
}
