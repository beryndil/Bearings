/**
 * Multi-select state for the sidebar session list — Phase 9a of
 * docs/context-menu-plan.md.
 *
 * Holds a `Set<string>` of selected session ids plus an `anchorId`
 * for Shift-click range selection. The SessionList component binds
 * Cmd/Ctrl+click to `toggle(id)` and Shift+click to `selectRange(id,
 * orderedList)`; a plain click clears the multi-selection and falls
 * through to the normal "select one" path owned by `sessions.select()`.
 *
 * Kept as its own store (not merged into `sessions.svelte`) so the
 * single-selection + open-session lifecycle stay isolated from the
 * bulk workflow — a user who never multi-selects pays zero cost.
 */

class SessionSelectionStore {
  /** Live set of selected session ids. Rendering uses `.has(id)`. */
  ids = $state<Set<string>>(new Set());

  /** Most recently clicked / toggled id. Shift-click ranges fan out
   * from this point. Null whenever the set is empty. */
  private anchorId: string | null = null;

  /** True when at least one session is selected — drives the
   * BulkActionBar visibility gate. Exposed as a method so $derived
   * consumers don't trigger Set iteration on every render. */
  hasSelection = $derived(this.ids.size > 0);

  /** Number of selected rows; shown in the bulk action bar's header. */
  size = $derived(this.ids.size);

  /** Toggle one id in/out. Called on Cmd/Ctrl+click. Sets the anchor
   * to `id` regardless of the toggle direction so a subsequent
   * Shift-click ranges off the most recent click. */
  toggle(id: string): void {
    const next = new Set(this.ids);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    this.ids = next;
    this.anchorId = next.size === 0 ? null : id;
  }

  /** Range-select from anchor (inclusive) to `id` (inclusive) using
   * the given ordered list as the authoritative sequence. If there's
   * no anchor yet this behaves like a single-row toggle so Shift-click
   * on an empty selection still lands somewhere reasonable. */
  selectRange(id: string, orderedIds: readonly string[]): void {
    if (this.anchorId === null) {
      this.toggle(id);
      return;
    }
    const anchorIndex = orderedIds.indexOf(this.anchorId);
    const clickIndex = orderedIds.indexOf(id);
    if (anchorIndex < 0 || clickIndex < 0) {
      // Either endpoint isn't in the current filtered view — degrade
      // to a single-row toggle rather than selecting nothing.
      this.toggle(id);
      return;
    }
    const [lo, hi] =
      anchorIndex <= clickIndex ? [anchorIndex, clickIndex] : [clickIndex, anchorIndex];
    const next = new Set(this.ids);
    for (let i = lo; i <= hi; i++) next.add(orderedIds[i]);
    this.ids = next;
  }

  /** Replace the selection with exactly these ids. Used by "Select
   * all" and for restoring state after a navigation. */
  replace(ids: Iterable<string>): void {
    const next = new Set(ids);
    this.ids = next;
    this.anchorId = next.size === 0 ? null : [...next][next.size - 1];
  }

  /** Wipe the selection. Called after a successful bulk op, or when
   * the user presses Escape while the bulk action bar is visible. */
  clear(): void {
    this.ids = new Set();
    this.anchorId = null;
  }

  /** Drop one id from the selection without touching the anchor. Used
   * by the WS delete-event path so a bulk op that races a sidebar
   * tab's stale selection doesn't leak into the next bulk request. */
  drop(id: string): void {
    if (!this.ids.has(id)) return;
    const next = new Set(this.ids);
    next.delete(id);
    this.ids = next;
    if (this.anchorId === id) {
      this.anchorId = next.size === 0 ? null : [...next][next.size - 1];
    }
  }
}

export const sessionSelection = new SessionSelectionStore();
