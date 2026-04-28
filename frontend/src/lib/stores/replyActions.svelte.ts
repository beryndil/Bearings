/**
 * L4.3.2 — Reply-action store. Owns the modal's transient state for
 * a single in-flight sub-agent invocation: which message we're
 * previewing, the streaming text accumulator, terminal state, cost,
 * and the cancel handle. The modal component reads `state` directly
 * and dispatches via `start` / `close` / `cancel`.
 *
 * Why a store and not local component state: the action lives on a
 * `MessageTurn`, but the modal is rendered above the conversation
 * pane. Hoisting the lifecycle into a singleton store means the
 * button can fire-and-forget (`replyActions.start(...)`) and the
 * modal — wherever it's mounted — picks up the `open` flag. Same
 * pattern the approval gate uses, just tailored to a one-shot
 * request that has no reconnect-resume contract.
 *
 * Lifecycle:
 *   start(...)  → status='streaming', message recorded, stream attached
 *   token       → text appended, status stays 'streaming'
 *   complete    → status='complete', cost recorded
 *   error       → status='error', message captured
 *   cancel()    → aborts the stream, status='cancelled'
 *   close()     → resets to status='idle' (modal closed)
 */

import * as api from '$lib/api';
import type { Message, ReplyActionEvent, ReplyActionStreamHandle } from '$lib/api';

/** Discriminated state union — `status` tells the modal what to
 * render. `idle` = closed (no modal). The non-idle states share
 * `text`, `messageId`, etc. so the modal renders the same surface
 * for streaming/complete/error and only swaps the footer treatment.
 */
export type ReplyActionStatus = 'idle' | 'streaming' | 'complete' | 'error' | 'cancelled';

export type ReplyActionState = {
  status: ReplyActionStatus;
  /** The action that's running (e.g. 'summarize'). Empty when idle. */
  action: string;
  /** Human label from the catalog ('TL;DR', 'Critique'). Empty when idle. */
  label: string;
  /** Source assistant message id we're previewing. Null when idle. */
  messageId: string | null;
  /** Source session id (parent). Null when idle. */
  sessionId: string | null;
  /** Streamed body so far. Always reflects what the user sees. */
  text: string;
  /** SDK-reported cost (USD). Null until `complete`, or if the SDK
   * didn't report one. */
  costUsd: number | null;
  /** Error message when status='error'. Empty otherwise. */
  errorMessage: string;
};

const INITIAL_STATE: ReplyActionState = {
  status: 'idle',
  action: '',
  label: '',
  messageId: null,
  sessionId: null,
  text: '',
  costUsd: null,
  errorMessage: '',
};

class ReplyActionsStore {
  /** Modal-driving state. Reactive via Svelte 5 runes. */
  state = $state<ReplyActionState>({ ...INITIAL_STATE });
  /** Catalog of available actions (loaded lazily on first need). */
  catalog = $state<api.ReplyActionCatalog>({});
  /** Active stream handle so `cancel()` can abort. Cleared on
   * terminal events. */
  private handle: ReplyActionStreamHandle | null = null;

  /** Refresh the catalog from the server. Cheap — single GET. The
   * modal calls this on first open if the cache is empty. Errors
   * are swallowed: the modal still renders with a fallback label
   * derived from the action name. */
  async refreshCatalog(): Promise<void> {
    try {
      this.catalog = await api.fetchReplyActionsCatalog();
    } catch {
      // Non-fatal: a stale or empty catalog just means we render
      // the action name as the label. The stream still works.
    }
  }

  /** Start a sub-agent invocation. Cancels any in-flight stream
   * (one modal at a time) before kicking off the new one. The
   * modal opens immediately on `streaming` status so the user sees
   * "loading" framing before the first token lands. */
  start(action: string, msg: Message): void {
    this.cancel();
    const label = this.catalog[action]?.label ?? action;
    this.state = {
      status: 'streaming',
      action,
      label,
      messageId: msg.id,
      sessionId: msg.session_id,
      text: '',
      costUsd: null,
      errorMessage: '',
    };
    this.handle = api.streamReplyAction(msg.session_id, msg.id, action, (ev: ReplyActionEvent) =>
      this.handleEvent(ev)
    );
  }

  /** Wire-level event handler. Mutates `state` in place so the
   * modal re-renders. After a terminal event the handle is cleared
   * but state stays so the modal can show the result + Copy / Send
   * to composer. */
  private handleEvent(ev: ReplyActionEvent): void {
    if (this.state.status !== 'streaming') return; // closed mid-flight
    if (ev.type === 'token') {
      this.state = { ...this.state, text: this.state.text + ev.text };
      return;
    }
    if (ev.type === 'complete') {
      this.state = {
        ...this.state,
        status: 'complete',
        // Prefer the server's `full_text` since chunk concat is
        // exactly equivalent — but the server's value is the
        // canonical "what the model produced" so it wins on any
        // edge-case mismatch (rare).
        text: ev.full_text || this.state.text,
        costUsd: ev.cost_usd,
      };
      this.handle = null;
      return;
    }
    if (ev.type === 'error') {
      this.state = {
        ...this.state,
        status: 'error',
        errorMessage: ev.message,
      };
      this.handle = null;
    }
  }

  /** Abort the in-flight stream. State flips to `cancelled` IF
   * we're still mid-stream — terminal states are left alone so
   * a no-op cancel after `complete` doesn't blow away the result.
   * Idempotent. */
  cancel(): void {
    if (this.handle) {
      this.handle.cancel();
      this.handle = null;
    }
    if (this.state.status === 'streaming') {
      this.state = { ...this.state, status: 'cancelled' };
    }
  }

  /** Close the modal. Aborts any in-flight stream (cleanup) and
   * resets state to idle. The modal is the only `close` caller. */
  close(): void {
    this.cancel();
    this.state = { ...INITIAL_STATE };
  }
}

export const replyActions = new ReplyActionsStore();
