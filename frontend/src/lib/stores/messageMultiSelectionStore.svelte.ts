/**
 * Message-level multi-selection store — tracks the set of message IDs
 * currently selected within a conversation transcript via Ctrl+click.
 *
 * This is distinct from :mod:`multiSelection.svelte.ts` which operates on
 * session IDs in the sidebar. This store is scoped to the conversation
 * panel (T2-12) and drives the ``MENU_TARGET_MESSAGE_MULTI_SELECT`` context
 * menu when two or more messages are selected and the user right-clicks
 * any one of them.
 *
 * Consumers:
 *
 * - :class:`MessageTurn.svelte` — Ctrl+click toggles a message in/out;
 *   right-click on a selected message opens the multi-select menu when
 *   ``ids.size >= 1``.
 * - :class:`MessageList.svelte` (or equivalent container) — reads ``ids``
 *   to apply a visual "selected" ring on targeted bubbles.
 *
 * The selection is cleared when the active session changes (caller
 * responsibility — call :func:`clearMessageSelection` on session switch).
 */

interface MessageMultiSelectionState {
  /** Set of message IDs currently selected. Read-only externally. */
  ids: ReadonlySet<string>;
}

const state: MessageMultiSelectionState = $state({ ids: new Set<string>() });

/** Reactive snapshot. Read ``messageMultiSelectionStore.ids`` in ``$derived``. */
export const messageMultiSelectionStore = state;

/** Flip a single message ID in or out of the selection. */
export function toggleMessageId(messageId: string): void {
  const next = new Set(state.ids);
  if (next.has(messageId)) {
    next.delete(messageId);
  } else {
    next.add(messageId);
  }
  state.ids = next;
}

/** Empty the selection. */
export function clearMessageSelection(): void {
  if (state.ids.size === 0) return;
  state.ids = new Set<string>();
}

/** Test seam — resets to empty state. */
export function _resetMessageSelectionForTests(): void {
  state.ids = new Set<string>();
}
