/**
 * Code-block-target actions — Phase 6.
 *
 * Bound implicitly via the delegate action on `CollapsibleBody`
 * (`$lib/actions/contextmenu-delegate.ts`) — any `<div
 * data-bearings-code-block>` in rendered Markdown opens this menu on
 * right-click. The target carries a snapshot of the code (`text`) and
 * the fence language (`language | null`) taken from the DOM at click
 * time, so handlers never re-parse the Markdown source.
 *
 * Phase 6 ships the copy actions live. The "save to file" and "open
 * in editor" actions land disabled-with-tooltip: both need a tempfile
 * primitive (`/api/shell/save_temp` or similar) that the spec defers
 * until the shell layer grows past `open` — see plan §3.3 open
 * questions. Their IDs are reserved from day one so a future TOML
 * override works without a rename.
 */

import { writeClipboard } from '../clipboard';
import type { Action, CodeBlockTarget, ContextTarget } from '../types';

function asCodeBlock(t: ContextTarget): CodeBlockTarget | null {
  return t.type === 'code_block' ? t : null;
}

/** Rebuild the original triple-backtick fence. Uses the target's
 * captured language when present — an empty language tag is legal
 * Markdown but feels wrong in a paste, so we omit the tag when null.
 * A trailing newline is appended so pasting inside another Markdown
 * doc doesn't glue the closing fence to the next paragraph. */
function withFence(text: string, language: string | null): string {
  const fence = language ? `\`\`\`${language}\n` : '```\n';
  const body = text.endsWith('\n') ? text : `${text}\n`;
  return `${fence}${body}\`\`\`\n`;
}

export const CODE_BLOCK_ACTIONS: readonly Action[] = [
  {
    id: 'code_block.copy',
    label: 'Copy code',
    section: 'copy',
    mnemonic: 'c',
    handler: async ({ target }) => {
      const t = asCodeBlock(target);
      if (!t) return;
      await writeClipboard(t.text);
    },
  },
  {
    id: 'code_block.copy_with_fence',
    label: 'Copy with Markdown fence',
    section: 'copy',
    advanced: true,
    mnemonic: 'f',
    handler: async ({ target }) => {
      const t = asCodeBlock(target);
      if (!t) return;
      await writeClipboard(withFence(t.text, t.language));
    },
  },
  {
    id: 'code_block.save_to_file',
    label: 'Save to file…',
    section: 'edit',
    handler: () => {},
    disabled: () => 'Save-to-tempfile needs a new shell primitive (v0.10.x)',
  },
  {
    id: 'code_block.open_in.editor',
    label: 'Open in editor',
    section: 'edit',
    advanced: true,
    handler: () => {},
    disabled: () => 'Open-in-editor needs the tempfile primitive (v0.10.x)',
  },
];
