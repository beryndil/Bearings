/**
 * Pending-operation actions — Phase 16 of docs/context-menu-plan.md.
 *
 * Target: `PendingOperationTarget`, emitted by rows in the floating
 * `PendingOpsCard`. Every row is right-clickable with a four-action
 * menu (Resolve / Dismiss / Copy name / Open associated path in
 * editor). The card itself is the home for left-click resolve, but
 * the right-click menu is the discoverable surface for the supporting
 * verbs (copy name into a commit message, jump to the associated
 * file, etc.).
 *
 * Resolve and Dismiss both hit `pending.resolve(name, directory)` —
 * the underlying primitive is idempotent and the API doesn't
 * distinguish between "I finished it" and "skip it." The two action
 * IDs are kept separate because the UX vocabulary differs: Resolve
 * is the success path the user reaches for after fixing the issue;
 * Dismiss is the abandon path. Future: split into a real `dismiss`
 * primitive with a "won't fix" state if usage data shows the
 * distinction matters.
 */

import { openShell } from '$lib/api/shell';
import { pending } from '$lib/stores/pending.svelte';
import { writeClipboard } from '../clipboard';
import { stubStore } from '../stub.svelte';
import type { Action, ContextTarget, PendingOperationTarget } from '../types';

function asPending(t: ContextTarget): PendingOperationTarget | null {
  return t.type === 'pending_operation' ? t : null;
}

export const PENDING_OPERATION_ACTIONS: readonly Action[] = [
  {
    id: 'pending_operation.resolve',
    label: 'Mark resolved',
    section: 'primary',
    mnemonic: 'r',
    handler: async ({ target }) => {
      const t = asPending(target);
      if (!t) return;
      await pending.resolve(t.directory, t.name);
    },
  },
  {
    id: 'pending_operation.dismiss',
    label: 'Dismiss',
    section: 'destructive',
    destructive: true,
    handler: async ({ target }) => {
      const t = asPending(target);
      if (!t) return;
      await pending.dismiss(t.directory, t.name);
    },
  },
  {
    id: 'pending_operation.copy_name',
    label: 'Copy name',
    section: 'copy',
    handler: async ({ target }) => {
      const t = asPending(target);
      if (!t) return;
      await writeClipboard(t.name);
    },
  },
  {
    id: 'pending_operation.copy_command',
    label: 'Copy command',
    section: 'copy',
    advanced: true,
    handler: async ({ target }) => {
      const t = asPending(target);
      if (!t || !t.command) return;
      await writeClipboard(t.command);
    },
    disabled: (target) => {
      const t = asPending(target);
      if (!t) return null;
      return t.command ? null : 'No command attached to this pending op';
    },
  },
  {
    id: 'pending_operation.open_in.editor',
    label: 'Open directory in editor',
    section: 'view',
    advanced: true,
    handler: async ({ target }) => {
      const t = asPending(target);
      if (!t) return;
      try {
        await openShell('editor', t.directory);
      } catch (err) {
        stubStore.show({
          actionId: 'pending_operation.open_in.editor',
          reason: err instanceof Error ? err.message : String(err),
        });
      }
    },
  },
];
