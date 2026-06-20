/**
 * Fetch and cache the context-menu pin/hide overrides from
 * ``GET /api/ui-config`` (N-13; docs/behavior/context-menus.md).
 *
 * The promise is cached at module scope so repeated calls issue only
 * one network round-trip.  On failure an empty config (no pin, no hide)
 * is returned — failing open so the menus still render.
 */
import { getJson } from "../api/client";
import { API_UI_CONFIG_ENDPOINT } from "../config";

export interface MenusConfig {
  pin: readonly string[];
  hide: readonly string[];
}

const EMPTY: MenusConfig = { pin: [], hide: [] };

let _promise: Promise<MenusConfig> | null = null;

interface UiConfigContextMenus {
  context_menus?: { pin?: string[]; hide?: string[] };
}

export function fetchMenusConfig(): Promise<MenusConfig> {
  if (_promise === null) {
    _promise = getJson<UiConfigContextMenus>(API_UI_CONFIG_ENDPOINT)
      .then((data) => ({
        pin: data.context_menus?.pin ?? [],
        hide: data.context_menus?.hide ?? [],
      }))
      .catch(() => EMPTY);
  }
  return _promise;
}

/** Test seam — clears the cached promise so the next call re-fetches. */
export function _resetMenusConfigForTests(): void {
  _promise = null;
}
