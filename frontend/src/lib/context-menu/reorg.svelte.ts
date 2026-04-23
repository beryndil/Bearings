/**
 * Cross-component bridge between message-target actions and the
 * Conversation view's session-picker modal.
 *
 * Background: Phase 5 deletes the `⋯` popover that used to live on
 * every `MessageTurn` header. In the old flow the popover fired
 * `onMoveMessage` / `onSplitAfter` callbacks that Conversation.svelte
 * passed down as props. Registry-driven actions can't reach back up the
 * tree — they run with only a `ContextTarget` in hand and no reference
 * to the host component — so the handlers in `actions/message.ts`
 * publish to this store instead.
 *
 * Conversation.svelte subscribes via `$effect`, opens its picker when a
 * pending request targets its active session, and clears the pending
 * slot so the same request doesn't re-trigger on unrelated state
 * changes.
 *
 * Why a store and not a global `window.dispatchEvent` bus: the picker
 * must survive a navigation from SessionList (which re-mounts
 * Conversation with a new session id) without a stale event firing
 * against the new view. A store with an explicit `clear()` makes the
 * life-cycle obvious, and the state is Svelte-reactive so subscribers
 * don't need to wire up/tear down listeners.
 *
 * Scope: session reorg only. Don't grow this store into a general
 * "context-menu dispatch to hosting component" bus — each new bridge
 * of that shape should be its own tiny store so the contract stays
 * legible at the call site.
 */

export type ReorgRequest = {
  kind: 'move' | 'split';
  messageId: string;
  /** The message's session. Carried so Conversation can ignore
   * requests aimed at a session other than the one it's currently
   * rendering — a right-click on a stale background tab must not
   * open a picker in the foreground. */
  sessionId: string;
};

class ReorgStore {
  pending = $state<ReorgRequest | null>(null);

  request(req: ReorgRequest): void {
    this.pending = req;
  }

  clear(): void {
    this.pending = null;
  }
}

export const reorgStore = new ReorgStore();
