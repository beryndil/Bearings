/**
 * Attachment-target actions — Phase 14 of docs/context-menu-plan.md.
 *
 * Wired to the `[File N]` chip used by both the composer (pre-send)
 * and the transcript user bubble (post-send). The chip carries the
 * absolute on-disk path that the runner substituted into the prompt
 * before the SDK saw it, so every action here is a thin client-side
 * dispatch — copy text into the clipboard, or kick `/api/shell/open`
 * with the path. No new server primitive needed beyond the shell
 * bridge that already ships for the `open_in` submenu elsewhere.
 *
 * `attachment.remove` is the composer-only verb: it strips the chip
 * from the staged list. The post-send transcript chip uses the
 * `disabled` predicate to grey it out (you can't unsend bytes from
 * a turn already on disk).
 */

import { openShell, type ShellKind } from '$lib/api/shell';
import { writeClipboard } from '../clipboard';
import { stubStore } from '../stub.svelte';
import type { Action, AttachmentTarget, ContextTarget } from '../types';

function asAttachment(t: ContextTarget): AttachmentTarget | null {
  return t.type === 'attachment' ? t : null;
}

/** Attempt to dispatch the path through `/api/shell/open` with the
 * given kind. The call resolves to 204 on success; failure surfaces
 * as a stub toast naming the action so the user can see what missed
 * (typically "no command configured" — `config.toml` `shell.editor_command`
 * etc. govern). */
async function shellOpen(actionId: string, kind: ShellKind, path: string): Promise<void> {
  try {
    await openShell(kind, path);
  } catch (err) {
    stubStore.show({
      actionId,
      reason: err instanceof Error ? err.message : String(err)
    });
  }
}

export const ATTACHMENT_ACTIONS: readonly Action[] = [
  {
    id: 'attachment.copy_path',
    label: 'Copy path',
    section: 'copy',
    mnemonic: 'p',
    handler: async ({ target }) => {
      const t = asAttachment(target);
      if (!t) return;
      await writeClipboard(t.path);
    }
  },
  {
    id: 'attachment.copy_filename',
    label: 'Copy filename',
    section: 'copy',
    handler: async ({ target }) => {
      const t = asAttachment(target);
      if (!t) return;
      await writeClipboard(t.filename);
    }
  },
  {
    id: 'attachment.open_in.editor',
    label: 'Open in editor',
    section: 'view',
    mnemonic: 'e',
    handler: async ({ target }) => {
      const t = asAttachment(target);
      if (!t) return;
      await shellOpen('attachment.open_in.editor', 'editor', t.path);
    }
  },
  {
    id: 'attachment.open_in.file_explorer',
    label: 'Reveal in file explorer',
    section: 'view',
    advanced: true,
    handler: async ({ target }) => {
      const t = asAttachment(target);
      if (!t) return;
      await shellOpen('attachment.open_in.file_explorer', 'file_explorer', t.path);
    }
  },
  {
    id: 'attachment.remove',
    label: 'Remove from message',
    section: 'destructive',
    destructive: true,
    handler: ({ target }) => {
      const t = asAttachment(target);
      if (!t) return;
      // Composer-side removal is owned by Conversation.svelte, which
      // listens on this custom event and runs `removeAttachment(n)`.
      // Dispatching the event keeps the action target-agnostic — the
      // chip can sit anywhere in the DOM and the listener doesn't
      // care which slot fired it.
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('bearings:attachment-remove', { detail: { n: t.n } })
        );
      }
    },
    disabled: (target) => {
      const t = asAttachment(target);
      if (!t) return null;
      // Post-send chips have a real messageId — those bytes are
      // already in a sent turn and removing the chip would desync
      // the transcript from the sdk_session_id history.
      return t.messageId !== null
        ? 'Already sent — open the message context-menu to manage'
        : null;
    }
  }
];
