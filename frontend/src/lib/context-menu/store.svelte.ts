/**
 * Singleton context-menu store. Only one menu is open at a time; a
 * second right-click replaces the current menu rather than stacking.
 *
 * The store is intentionally minimal in Phase 1: open-state, target,
 * cursor coordinates, and the shift-was-held flag (advanced mode).
 * Keyboard focus and submenu-open state join in Phase 2.
 */

import type { ContextTarget } from './types';

type MenuState = {
  open: boolean;
  target: ContextTarget | null;
  x: number;
  y: number;
  advanced: boolean;
};

function initial(): MenuState {
  return { open: false, target: null, x: 0, y: 0, advanced: false };
}

class ContextMenuStore {
  state = $state<MenuState>(initial());

  open(target: ContextTarget, x: number, y: number, advanced: boolean): void {
    this.state.open = true;
    this.state.target = target;
    this.state.x = x;
    this.state.y = y;
    this.state.advanced = advanced;
  }

  close(): void {
    this.state.open = false;
    this.state.target = null;
  }
}

export const contextMenu = new ContextMenuStore();
