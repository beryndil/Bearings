/**
 * Reorg mutation flows for the Conversation pane.
 *
 * Owns the full move/split/merge plumbing — server calls, optimistic
 * undo state, audit-row cleanup, and the post-op "reconcile sidebar +
 * conversation + audits" cycle. Lives outside `Conversation.svelte`
 * so the parent shrinks under the project's 400-line cap, and the
 * undo-state shape gets a unit-test surface.
 *
 * Used as a per-Conversation instance (not a singleton): undo is
 * tab-local, so each pane gets its own controller. Mutation flows
 * import the `sessions` / `conversation` / `api` singletons directly
 * — they're already module-scoped stores — but the bulk-mode reset
 * and bulk-id snapshot enter via the `ops` bag so this module never
 * needs to know about `BulkModeController` directly.
 */

import * as api from '$lib/api';
import { conversation } from '$lib/stores/conversation.svelte';
import { sessions } from '$lib/stores/sessions.svelte';

/** Pending undo toast — one at a time. A new reorg op replaces it,
 * which is the desired behavior: the UI only guarantees Undo for the
 * most-recent op. The closure captured in `run` is pure per-op; the
 * parent clears `undo` on dismiss/undo. */
export type ReorgUndoState = {
  message: string;
  /** Tool-call-group split flags the server surfaced for this op.
   * Rendered above the message in the toast so the user sees them
   * before tapping Undo. Empty for well-formed ops (the common case). */
  warnings: api.ReorgWarning[];
  run: () => Promise<void>;
};

/** Optional draft for the "create a new session" path on split /
 * bulk-split. Mirrors `SessionPickerModal`'s create-form payload. */
export type ReorgNewSessionDraft = {
  title: string;
  tag_ids: number[];
};

/** Picker context handed to `pickerPickExisting` / `pickerPickNew`.
 * Matches the snapshot Conversation captures at picker-confirm so the
 * op stays stable even if the user tweaks the selection mid-modal. */
export type ReorgPickerContext = {
  op: 'move' | 'split' | 'bulk-move' | 'bulk-split' | 'merge';
  /** Anchor message for the per-message ⋯ flows; null for bulk +
   * merge variants. */
  anchor: api.Message | null;
  /** Snapshot of bulk-selected ids; empty for non-bulk variants. */
  bulkIds: string[];
};

/** Callback bag the controller needs to coordinate with the rest of
 * Conversation. Kept narrow on purpose: anything that crosses into
 * reactive component state goes through here, and shared singletons
 * (`sessions`, `conversation`, `api`) are imported directly. */
export type ReorgOps = {
  /** Exit bulk-select mode after a successful bulk op — the affected
   * rows have left this view, so dangling checkboxes would confuse. */
  exitBulkMode: () => void;
};

/** Wrap an undo closure with audit-row cleanup. If the server
 * returned an `audit_id`, the divider is removed as part of the undo
 * so the user doesn't see a stale "Moved N messages to X" line for an
 * op that was reversed. The delete is scoped to `sourceId` and
 * swallows 404s — a second-click race against the user manually
 * deleting the divider should not blow up the undo. */
async function deleteAuditSafe(
  sourceId: string,
  auditId: number | null
): Promise<void> {
  if (auditId == null) return;
  try {
    await api.deleteReorgAudit(sourceId, auditId);
  } catch {
    // Row was already gone — fine, undo still succeeded.
  }
}

export class ReorgController {
  /** Currently-pending undo toast. Replaced (not queued) on every op
   * — a new reorg op moots the prior undo. */
  undo = $state<ReorgUndoState | null>(null);

  constructor(private ops: ReorgOps) {}

  /** Dismiss the undo toast without running its inverse. Bound to the
   * toast's ✕ button. */
  dismissUndo(): void {
    this.undo = null;
  }

  /** Re-pull the audit list for the active session. Defensive: if the
   * user navigated away mid-fetch, the result is dropped. Non-fatal —
   * a failed audit fetch just leaves the timeline without dividers. */
  async refreshAudits(): Promise<void> {
const sid = sessions.selectedId;
    if (!sid) return;
    try {
      const rows = await api.listReorgAudits(sid);
      if (sessions.selectedId === sid) conversation.setAudits(sid, rows);
    } catch {
      // Non-fatal — the conversation still renders without dividers.
    }
  }

  /** Run after a successful op so the view reconciles against the
   * server. Refreshes the sidebar + active conversation so moved rows
   * disappear immediately instead of waiting for the next event. Also
   * re-pulls the audit list when the current session is on either end
   * of the op — new/undone dividers surface without a reload. */
  async reconcileAfterReorg(affectedIds: string[]): Promise<void> {
await sessions.refresh(sessions.filter);
    const currentSid = sessions.selectedId;
    if (currentSid && affectedIds.includes(currentSid)) {
      await conversation.load(currentSid);
      await this.refreshAudits();
    }
  }

  /** Single-message move to an existing target. Undo runs the inverse
   * `reorgMove` and clears the audit divider. */
  async doMove(
    sourceId: string,
    msgId: string,
    targetSessionId: string,
    label: string
  ): Promise<void> {
try {
      const result = await api.reorgMove(sourceId, {
        target_session_id: targetSessionId,
        message_ids: [msgId]
      });
      await this.reconcileAfterReorg([sourceId, targetSessionId]);
      const auditId = result.audit_id;
      this.undo = {
        message: `Moved ${result.moved} message to ${label}.`,
        warnings: result.warnings,
        run: async () => {
          await api.reorgMove(targetSessionId, {
            target_session_id: sourceId,
            message_ids: [msgId]
          });
          await deleteAuditSafe(sourceId, auditId);
          await this.reconcileAfterReorg([sourceId, targetSessionId]);
        }
      };
    } catch (e) {
      conversation.error = e instanceof Error ? e.message : String(e);
    }
  }

  /** Bulk move of an explicit id list into an existing target. Undo
   * is a straight reverse move — no session cleanup needed unless
   * `deleteTargetOnUndo` is set (the bulk-split-to-new flow uses this
   * to discard the just-created destination on undo). Exits bulk mode
   * on success so the now-orphaned checkboxes go away. */
  async doBulkMove(
    sourceId: string,
    msgIds: string[],
    targetSessionId: string,
    label: string,
    deleteTargetOnUndo = false
  ): Promise<void> {
try {
      const result = await api.reorgMove(sourceId, {
        target_session_id: targetSessionId,
        message_ids: msgIds
      });
      await this.reconcileAfterReorg([sourceId, targetSessionId]);
      this.ops.exitBulkMode();
      const plural = result.moved === 1 ? '' : 's';
      const auditId = result.audit_id;
      this.undo = {
        message: `Moved ${result.moved} message${plural} to ${label}.`,
        warnings: result.warnings,
        run: async () => {
          await api.reorgMove(targetSessionId, {
            target_session_id: sourceId,
            message_ids: msgIds
          });
          if (deleteTargetOnUndo) {
            // Deleting the target cascades the audit row automatically,
            // so we skip the explicit delete in that branch.
            await api.deleteSession(targetSessionId);
          } else {
            await deleteAuditSafe(sourceId, auditId);
          }
          await this.reconcileAfterReorg([sourceId, targetSessionId]);
        }
      };
    } catch (e) {
      conversation.error = e instanceof Error ? e.message : String(e);
    }
  }

  /** Split off everything after `anchorMsgId` into a freshly-created
   * session. Inverse is "move everything back + delete the new
   * session"; deleting the new session cascades its audit row, so no
   * explicit deleteReorgAudit call needed. */
  async doSplit(
    sourceId: string,
    anchorMsgId: string,
    draft: ReorgNewSessionDraft
  ): Promise<void> {
try {
      const result = await api.reorgSplit(sourceId, {
        after_message_id: anchorMsgId,
        new_session: { title: draft.title, tag_ids: draft.tag_ids }
      });
      await this.reconcileAfterReorg([sourceId, result.session.id]);
      const newId = result.session.id;
      const movedCount = result.result.moved;
      this.undo = {
        message: `Split off ${movedCount} message${movedCount === 1 ? '' : 's'} into "${
          result.session.title ?? '(untitled)'
        }".`,
        warnings: result.result.warnings,
        run: async () => {
          const rows = await api.listMessages(newId);
          if (rows.length > 0) {
            await api.reorgMove(newId, {
              target_session_id: sourceId,
              message_ids: rows.map((m) => m.id)
            });
          }
          await api.deleteSession(newId);
          await this.reconcileAfterReorg([sourceId, newId]);
        }
      };
    } catch (e) {
      conversation.error = e instanceof Error ? e.message : String(e);
    }
  }

  /** Fold the entire source into `targetSessionId`. The frontend
   * always passes `delete_source=false` — keeping the source alive so
   * the user has somewhere to render the audit divider and hit Undo
   * from. If they really want the source gone they can delete it by
   * hand after the undo window lapses.
   *
   * Snapshots the source's message ids BEFORE the merge so the undo
   * knows exactly which rows to move back — `move_messages_tx`
   * preserves `created_at`, so "the N newest rows on the target"
   * isn't necessarily "the ones we just moved over." */
  async doMerge(
    sourceId: string,
    targetSessionId: string,
    label: string
  ): Promise<void> {
try {
      const sourceRows = await api.listMessages(sourceId);
      const sourceIds = sourceRows.map((m) => m.id);
      const result = await api.reorgMerge(sourceId, {
        target_session_id: targetSessionId,
        delete_source: false
      });
      await this.reconcileAfterReorg([sourceId, targetSessionId]);
      const auditId = result.audit_id;
      const movedCount = result.moved;
      const plural = movedCount === 1 ? '' : 's';
      this.undo = {
        message:
          movedCount === 0
            ? `No messages to merge into ${label}.`
            : `Merged ${movedCount} message${plural} into ${label}.`,
        warnings: result.warnings,
        run: async () => {
          if (sourceIds.length > 0) {
            await api.reorgMove(targetSessionId, {
              target_session_id: sourceId,
              message_ids: sourceIds
            });
          }
          await deleteAuditSafe(sourceId, auditId);
          await this.reconcileAfterReorg([sourceId, targetSessionId]);
        }
      };
    } catch (e) {
      conversation.error = e instanceof Error ? e.message : String(e);
    }
  }

  /** Picker confirmed against an existing target session. Branches
   * by `op` to dispatch the right do* call. Split-into-existing is
   * routed through `doBulkMove` because semantically the user picked
   * an existing session, which collapses to a bulk-move of the post-
   * anchor ids. Closing the picker is the caller's job. */
  async pickerPickExisting(
    targetId: string,
    ctx: ReorgPickerContext
  ): Promise<void> {
const sourceId = sessions.selectedId;
    if (!sourceId) return;
    const targetLabel =
      sessions.list.find((s) => s.id === targetId)?.title ?? 'session';

    if (ctx.op === 'bulk-move' || ctx.op === 'bulk-split') {
      // Split-into-existing collapses to a bulk move against the
      // chosen target. The user opened the picker in "split into new"
      // mode but backed out to pick an existing row — that's
      // semantically a bulk move, so treat it that way.
      if (ctx.bulkIds.length === 0) return;
      await this.doBulkMove(sourceId, ctx.bulkIds, targetId, `"${targetLabel}"`);
      return;
    }
    if (ctx.op === 'merge') {
      await this.doMerge(sourceId, targetId, `"${targetLabel}"`);
      return;
    }
    if (!ctx.anchor) return;
    if (ctx.op === 'move') {
      await this.doMove(sourceId, ctx.anchor.id, targetId, `"${targetLabel}"`);
      return;
    }
    // Split into an EXISTING session = "move everything after anchor
    // over there." No new session created, so we reuse the move route
    // with the collected post-anchor ids.
    const all = conversation.messages;
    const idx = all.findIndex((m) => m.id === ctx.anchor!.id);
    if (idx < 0) return;
    const toMove = all.slice(idx + 1).map((m) => m.id);
    if (toMove.length === 0) {
      conversation.error = 'No messages after the anchor to split.';
      return;
    }
    await this.doBulkMove(sourceId, toMove, targetId, `"${targetLabel}"`);
  }

  /** Picker confirmed against a brand-new session. For split/anchor
   * flows, defers to `doSplit` (server-side new-session creation in a
   * single round-trip). For bulk variants and single-message moves to
   * a new target, creates an empty session up front, then dispatches
   * the corresponding move. Closing the picker is the caller's job. */
  async pickerPickNew(
    draft: ReorgNewSessionDraft,
    ctx: ReorgPickerContext
  ): Promise<void> {
const sourceId = sessions.selectedId;
    if (!sourceId) return;

    if (ctx.op === 'split' && ctx.anchor) {
      await this.doSplit(sourceId, ctx.anchor.id, draft);
      return;
    }
    if (ctx.op === 'bulk-move' || ctx.op === 'bulk-split') {
      if (ctx.bulkIds.length === 0) return;
      const created = await this.createEmptySession(sourceId, draft);
      if (!created) return;
      await this.doBulkMove(
        sourceId,
        ctx.bulkIds,
        created.id,
        `"${created.title ?? '(untitled)'}"`,
        true
      );
      return;
    }
    if (!ctx.anchor) return;
    // Single-message move to a brand-new session: create the row,
    // then move. Use the api call directly (not sessions.create) so
    // we don't flip the selected session out from under the user
    // mid-triage. `reconcileAfterReorg` refreshes the sidebar list.
    const created = await this.createEmptySession(sourceId, draft);
    if (!created) return;
    await this.doMove(
      sourceId,
      ctx.anchor.id,
      created.id,
      `"${created.title ?? '(untitled)'}"`
    );
  }

  /** Direct API session-create that mirrors the source's
   * `working_dir` + `model`. Bypasses `sessions.create` so the
   * selected-session-pointer doesn't flip out from under the user
   * during a reorg. Surfaces creation errors via `conversation.error`. */
  async createEmptySession(
    sourceId: string,
    draft: ReorgNewSessionDraft
  ): Promise<api.Session | null> {
const source = sessions.list.find((s) => s.id === sourceId);
    if (!source) return null;
    try {
      return await api.createSession({
        working_dir: source.working_dir,
        model: source.model,
        title: draft.title,
        tag_ids: draft.tag_ids
      });
    } catch (e) {
      conversation.error = e instanceof Error ? e.message : String(e);
      return null;
    }
  }
}
