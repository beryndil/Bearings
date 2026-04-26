/**
 * Bulk-select mode controller for the Conversation pane.
 *
 * A lightweight parallel lane on top of the existing reorg flows:
 * checkboxes on each row, a floating action bar (rendered separately
 * by `BulkActionBar.svelte`), and shift-click range selection. While
 * active, `MessageTurn` hides its per-message ⋯ menu so the two
 * surfaces don't compete.
 *
 * Lives outside `Conversation.svelte` so the parent component shrinks
 * and the selection invariants get a unit-test surface
 * (`bulk-mode.test.ts`). Used as a per-Conversation instance, not a
 * singleton — each Conversation gets its own controller because bulk
 * selection is tab-local.
 */

import type * as api from '$lib/api';

export class BulkModeController {
  /** True while bulk-select mode is active. Drives the checkbox
   * column, the floating action bar's visibility, and the "hide my
   * own menu" branch in `MessageTurn`. */
  active = $state(false);

  /** Set of message ids currently checked. Reassigned (not mutated)
   * on every change so Svelte 5 sees a fresh reference and any
   * `$derived` consumer reruns. */
  selectedIds = $state<Set<string>>(new Set());

  /** Anchor for shift-click range selection: the last id the user
   * clicked. Reset alongside `selectedIds` on session switch / mode
   * exit so the next click can't extend across an unrelated thread. */
  lastSelectedId = $state<string | null>(null);

  /** Number of currently selected messages — drives the floating
   * action bar's count + plural labels. */
  get count(): number {
    return this.selectedIds.size;
  }

  /** Snapshot of selected ids as a stable array. Useful for handing
   * off to a reorg op without exposing the live Set. */
  ids(): string[] {
    return [...this.selectedIds];
  }

  /** Toggle bulk-mode entry/exit. Exiting clears the selection so
   * checkboxes don't dangle if the user re-enters mid-thread. */
  toggle(): void {
    this.active = !this.active;
    if (!this.active) this.clear();
  }

  /** Clear selection (and the shift-click anchor) without touching
   * `active`. Used after a successful bulk op (the affected rows are
   * gone from this view, so the checkboxes would dangle) and on
   * session-switch resets. */
  clear(): void {
    this.selectedIds = new Set();
    this.lastSelectedId = null;
  }

  /** Click on a row's checkbox. Shift-click extends from the last-
   * clicked row to the current one (range selection). Plain click
   * toggles just that one row. `all` is the full message list in
   * timeline order so the range bounds resolve correctly. */
  toggleSelect(msg: api.Message, shiftKey: boolean, all: api.Message[]): void {
    if (shiftKey && this.lastSelectedId) {
      const a = all.findIndex((m) => m.id === this.lastSelectedId);
      const b = all.findIndex((m) => m.id === msg.id);
      if (a >= 0 && b >= 0) {
        const [lo, hi] = a < b ? [a, b] : [b, a];
        const next = new Set(this.selectedIds);
        for (let i = lo; i <= hi; i++) next.add(all[i].id);
        this.selectedIds = next;
        this.lastSelectedId = msg.id;
        return;
      }
    }
    const next = new Set(this.selectedIds);
    if (next.has(msg.id)) next.delete(msg.id);
    else next.add(msg.id);
    this.selectedIds = next;
    this.lastSelectedId = msg.id;
  }
}
