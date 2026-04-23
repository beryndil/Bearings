/**
 * Link-target actions — Phase 6.
 *
 * Bound via the delegate action in `CollapsibleBody` — any `<a href>`
 * rendered by marked inside a message body opens this menu on
 * right-click. `href` is untrusted content (user- or agent-authored)
 * so every handler treats it defensively: `open_new_tab` goes through
 * `window.open` with `noopener,noreferrer`; `open_in.editor` gates on
 * a `file://` scheme and extracts the raw path before handing it to
 * `/api/shell/open`.
 *
 * Phase 6 ships all four actions live. The open-in.editor row stays
 * visible but disabled-with-tooltip on non-file URLs rather than
 * hiding outright — the user's eye remembers menu geometry across
 * right-clicks, and a flickering menu burns that memory.
 */

import * as api from '$lib/api';
import { writeClipboard } from '../clipboard';
import { stubStore } from '../stub.svelte';
import type { Action, ContextTarget, LinkTarget } from '../types';

function asLink(t: ContextTarget): LinkTarget | null {
  return t.type === 'link' ? t : null;
}

/** Parse a `file://…` URL into a host-side absolute path. Returns
 * null on anything else (http, relative, malformed). Guarded by a
 * try/catch because `new URL(href)` throws on relative URLs — we
 * don't want the menu to crash mid-render. */
function filePathFromHref(href: string): string | null {
  try {
    const u = new URL(href);
    if (u.protocol !== 'file:') return null;
    // decodeURIComponent rather than `pathname` directly so percent-
    // encoded spaces in paths round-trip cleanly into the shell.
    return decodeURIComponent(u.pathname);
  } catch {
    return null;
  }
}

export const LINK_ACTIONS: readonly Action[] = [
  {
    id: 'link.copy_url',
    label: 'Copy link URL',
    section: 'copy',
    mnemonic: 'u',
    handler: async ({ target }) => {
      const t = asLink(target);
      if (!t) return;
      await writeClipboard(t.href);
    }
  },
  {
    id: 'link.copy_text',
    label: 'Copy link text',
    section: 'copy',
    advanced: true,
    mnemonic: 't',
    handler: async ({ target }) => {
      const t = asLink(target);
      if (!t) return;
      await writeClipboard(t.text);
    }
  },
  {
    id: 'link.open_new_tab',
    label: 'Open in new tab',
    section: 'navigate',
    mnemonic: 'o',
    handler: ({ target }) => {
      const t = asLink(target);
      if (!t) return;
      if (typeof window === 'undefined') return;
      // `noopener,noreferrer` severs the reverse reference so an
      // untrusted agent link can't reach back into this window.
      window.open(t.href, '_blank', 'noopener,noreferrer');
    }
  },
  {
    id: 'link.open_in.editor',
    label: 'Open in editor',
    section: 'navigate',
    advanced: true,
    handler: async ({ target }) => {
      const t = asLink(target);
      if (!t) return;
      const path = filePathFromHref(t.href);
      if (!path) return;
      try {
        await api.openShell('editor', path);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        stubStore.show({
          actionId: 'link.open_in.editor',
          reason: msg.includes('shell.')
            ? `Configure ${msg} in config.toml`
            : `Shell dispatch failed: ${msg}`
        });
      }
    },
    disabled: (target) => {
      const t = asLink(target);
      if (!t) return null;
      if (filePathFromHref(t.href) === null) {
        return 'Editor open only works for file:// URLs';
      }
      return null;
    }
  }
];
