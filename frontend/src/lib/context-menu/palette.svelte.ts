/**
 * Command-palette open/close state. Singleton; only one palette visible
 * at a time (like the context menu, like CheatSheet). Separate from the
 * context-menu store because opening one must not close the other
 * by accident — but at the point one opens, the other should close
 * (callers handle that via effect chains).
 *
 * Shortcut binding lives in `+page.svelte` (global keydown listener)
 * rather than in this module so the page layout stays the single owner
 * of global shortcuts.
 */

class PaletteStore {
  open = $state(false);
  /** The query text. Persists between opens within the tab — power
   * users often re-run the same action, so the first keystroke after
   * re-opening should either clear the field via Esc or filter to the
   * same family. Cleared explicitly on `close()`. */
  query = $state('');

  show(): void {
    this.open = true;
    this.query = '';
  }

  hide(): void {
    this.open = false;
    this.query = '';
  }

  toggle(): void {
    if (this.open) this.hide();
    else this.show();
  }
}

export const palette = new PaletteStore();
