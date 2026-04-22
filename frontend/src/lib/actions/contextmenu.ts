/**
 * Svelte `use:contextmenu` action. Attach to any element that should
 * open the context menu on right-click or long-press (Phase 11 adds
 * the long-press arm).
 *
 * Usage:
 *   <li use:contextmenu={{ target: { type: 'session', id: session.id } }}>
 *
 * Decision §2.5:
 *   - Shift-right-click → open in advanced mode.
 *   - Ctrl+Shift+right-click → pass through to the browser's native
 *     context menu (dev escape hatch).
 *   - Plain right-click → open in normal mode.
 */

import { contextMenu } from '$lib/context-menu/store.svelte';
import type { ContextTarget } from '$lib/context-menu/types';

export type ContextMenuBinding = {
  /** null → attached but inert. Used for transient targets like a
   * still-streaming assistant bubble that has no message id yet. */
  target: ContextTarget | null;
};

export function contextmenu(
  node: HTMLElement,
  binding: ContextMenuBinding
): { update: (next: ContextMenuBinding) => void; destroy: () => void } {
  let current: ContextMenuBinding = binding;

  function onContextMenu(e: MouseEvent): void {
    // Ctrl+Shift+right-click → let Chrome's native menu fire.
    if (e.ctrlKey && e.shiftKey) return;
    if (current.target === null) return; // fall through to native menu
    e.preventDefault();
    e.stopPropagation();
    contextMenu.open(current.target, e.clientX, e.clientY, e.shiftKey);
  }

  node.addEventListener('contextmenu', onContextMenu);

  return {
    update(next: ContextMenuBinding): void {
      current = next;
    },
    destroy(): void {
      node.removeEventListener('contextmenu', onContextMenu);
    }
  };
}
