/**
 * Composer bridge — small store the vault pane writes paste-into-
 * composer requests into and the conversation composer (when it lands
 * post-2.3) reads from.
 *
 * Per ``docs/behavior/vault.md`` §"Paste-into-message behavior" the
 * vault row exposes "Paste link into composer" + "Paste body into
 * composer" affordances that target the active chat session. The
 * vault pane and the composer live in different parts of the app
 * shell; piping the paste through a shared store keeps the two ends
 * decoupled — the vault pane doesn't have to know which composer
 * implementation is mounted, and the composer doesn't have to know
 * which surface initiated the paste.
 *
 * Shape: a single ``pending`` slot (one paste at a time — the user
 * is unlikely to fire two pastes in the same animation frame, and
 * keeping a queue would add ordering questions the behavior doc is
 * silent on). The composer reads ``pending``, applies it to the
 * draft, and calls :func:`consumePendingPaste` to clear the slot.
 */

/** One paste request — text targeted at one chat session's composer. */
export interface PendingPaste {
  /** Session whose composer should receive the paste. */
  sessionId: string;
  /** Text to splice into the composer at the cursor (or end-of-buffer). */
  text: string;
  /**
   * Discriminator for telemetry / toast wording — ``"link"`` is the
   * Markdown title-as-link path; ``"body"`` is the full doc body
   * paste. The composer doesn't branch on the value beyond surfacing
   * a different toast.
   */
  kind: "link" | "body";
}

interface ComposerBridgeState {
  /** Pending paste, or ``null`` when no paste is queued. */
  pending: PendingPaste | null;
}

const state: ComposerBridgeState = $state({
  pending: null,
});

export const composerBridgeStore = state;

/**
 * Queue a paste request for ``sessionId``'s composer. Replaces any
 * previous unread pending paste — the latest user gesture wins.
 */
export function pasteIntoComposer(paste: PendingPaste): void {
  state.pending = paste;
}

/**
 * Consume the pending paste — the composer calls this after applying
 * the paste to its draft. Returns the consumed value so the composer
 * can branch on the kind for toast wording.
 */
export function consumePendingPaste(): PendingPaste | null {
  const consumed = state.pending;
  state.pending = null;
  return consumed;
}

/** Test seam — restores the boot state without re-importing the module. */
export function _resetForTests(): void {
  state.pending = null;
}
