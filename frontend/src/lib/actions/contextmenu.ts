/**
 * Svelte `use:contextmenu` action. Attach to any element that should
 * open the context menu on right-click or long-press.
 *
 * Usage:
 *   <li use:contextmenu={{ target: { type: 'session', id: session.id } }}>
 *
 * Decision §2.5:
 *   - Shift-right-click → open in advanced mode.
 *   - Ctrl+Shift+right-click → pass through to the browser's native
 *     context menu (dev escape hatch).
 *   - Plain right-click → open in normal mode.
 *
 * Phase 11 long-press arm (spec §6.4):
 *   - On coarse pointers (`@media (pointer: coarse)`), a 500ms
 *     pointerdown with <=8px movement opens the same menu in normal
 *     mode (no Shift → no advanced; Shift-long-press isn't a thing on
 *     touch).
 *   - Regular taps and drags pass through untouched.
 *   - The underlying FSM lives in `$lib/context-menu/touch` and is
 *     unit-tested there.
 */

import { contextMenu } from '$lib/context-menu/store.svelte';
import { longpress } from '$lib/context-menu/touch';
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

  // Wire the same "open menu" path to long-press. The `longpress`
  // action handles coarse-pointer gating, movement threshold, and
  // timer bookkeeping — this binding just needs to know what target to
  // open and where. A null target still skips the open, matching the
  // right-click behaviour above.
  const longpressHandle = longpress(node, {
    onLongPress: (x, y) => {
      if (current.target === null) return;
      contextMenu.open(current.target, x, y, false);
    }
  });

  return {
    update(next: ContextMenuBinding): void {
      current = next;
      longpressHandle.update({
        onLongPress: (x, y) => {
          if (current.target === null) return;
          contextMenu.open(current.target, x, y, false);
        }
      });
    },
    destroy(): void {
      node.removeEventListener('contextmenu', onContextMenu);
      longpressHandle.destroy();
    }
  };
}
