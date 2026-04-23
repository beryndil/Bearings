/**
 * Checkpoint-target actions — Phase 7.3 of docs/context-menu-plan.md.
 *
 * Target: `CheckpointTarget`, emitted by gutter chips in
 * `CheckpointGutter.svelte`. Every chip is right-clickable with these
 * three actions; the fork action is additionally wired to the chip's
 * click handler so the headline "click to fork" flow matches the right-
 * click menu's primary item.
 *
 * `checkpoint.fork` gates on `messageId !== null` so orphaned rows (a
 * reorg audit dropped the anchor, FK SET NULL fired) render the fork
 * item greyed with a tooltip. The server enforces the same check with
 * a 400, but gating client-side avoids a round-trip for a failure the
 * UI already knows about.
 *
 * `checkpoint.delete` is destructive but not confirmation-gated: the
 * row is cheap to recreate (just re-anchor on the same message), and
 * Phase 6 undo toast covers the "I didn't mean it" case. If we learn
 * users find it too easy to lose a labelled checkpoint we'll wrap with
 * `confirmStore` like `session.delete`.
 */

import { checkpoints } from '$lib/stores/checkpoints.svelte';
import { sessions } from '$lib/stores/sessions.svelte';
import { writeClipboard } from '../clipboard';
import { undoStore } from '../undo.svelte';
import type { Action, CheckpointTarget, ContextTarget } from '../types';

function asCheckpoint(t: ContextTarget): CheckpointTarget | null {
  return t.type === 'checkpoint' ? t : null;
}

export const CHECKPOINT_ACTIONS: readonly Action[] = [
  {
    id: 'checkpoint.fork',
    label: 'Fork from here',
    section: 'primary',
    mnemonic: 'f',
    handler: async ({ target }) => {
      const t = asCheckpoint(target);
      if (!t) return;
      const forked = await checkpoints.fork(t.sessionId, t.id);
      if (forked) sessions.select(forked.id);
    },
    disabled: (target) => {
      const t = asCheckpoint(target);
      if (!t) return null;
      return t.messageId === null
        ? 'Anchor message was dropped in a reorg — fork unavailable'
        : null;
    }
  },
  {
    id: 'checkpoint.copy_label',
    label: 'Copy label',
    section: 'copy',
    handler: async ({ target }) => {
      const t = asCheckpoint(target);
      if (!t) return;
      await writeClipboard(t.label ?? '');
    },
    disabled: (target) => {
      const t = asCheckpoint(target);
      if (!t) return null;
      return t.label === null || t.label === ''
        ? 'No label to copy'
        : null;
    }
  },
  {
    id: 'checkpoint.copy_id',
    label: 'Copy checkpoint ID',
    section: 'copy',
    advanced: true,
    handler: async ({ target }) => {
      const t = asCheckpoint(target);
      if (!t) return;
      await writeClipboard(t.id);
    }
  },
  {
    id: 'checkpoint.delete',
    label: 'Delete checkpoint',
    section: 'destructive',
    destructive: true,
    mnemonic: 'd',
    handler: async ({ target }) => {
      const t = asCheckpoint(target);
      if (!t) return;
      // Snapshot the row before delete so the undo inverse can
      // recreate it. The recreation re-issues a POST — a fresh id is
      // assigned server-side, which is fine: the only externally-
      // visible property is the label, and that round-trips verbatim.
      const prev = { sessionId: t.sessionId, messageId: t.messageId, label: t.label };
      const removed = await checkpoints.remove(t.sessionId, t.id);
      if (!removed) return;
      if (prev.messageId === null) return; // orphan — can't recreate
      const anchorId = prev.messageId;
      undoStore.push({
        message: prev.label ? `Checkpoint "${prev.label}" deleted` : 'Checkpoint deleted',
        inverse: async () => {
          await checkpoints.create(prev.sessionId, anchorId, prev.label);
        }
      });
    }
  }
];
