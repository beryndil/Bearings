/**
 * Multi-select actions — Phase 9a of docs/context-menu-plan.md.
 *
 * Handlers fire against the server's one-endpoint `/sessions/bulk`
 * dispatcher. Every action shares the same shape: snapshot the
 * selection from the target (not the live store — a mid-menu WS
 * mutation shouldn't change which ids the user is acting on), POST
 * the bulk op, then clear the selection and let the sidebar's WS
 * subscription reconcile.
 *
 * The destructive `multi_select.delete` routes through `confirmStore`
 * to match the single-session delete UX. `multi_select.export` writes
 * the returned bundle to a downloaded JSON file via a temporary
 * `<a>` element — no server-side streaming response needed because the
 * payload is small (a handful of sessions) and the whole thing already
 * fits in memory by the time the bulk endpoint returns.
 */

import * as api from '$lib/api';
import { sessionSelection } from '$lib/stores/session_selection.svelte';
import { sessions } from '$lib/stores/sessions.svelte';
import { tags } from '$lib/stores/tags.svelte';
import { confirmStore } from '../confirm.svelte';
import type { Action, ContextTarget, MultiSelectTarget } from '../types';

function asMulti(t: ContextTarget): MultiSelectTarget | null {
  return t.type === 'multi_select' ? t : null;
}

/** Drop a Blob as a download without keeping a stray `<a>` in the DOM.
 * Purely browser-side — never called in the test harness, so the
 * `document`/`URL` lookups are fine as direct globals. */
function downloadBlob(blob: Blob, filename: string): void {
  if (typeof document === 'undefined' || typeof URL === 'undefined') return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function tagSubmenuItem(tag: api.Tag, op: 'tag' | 'untag'): Action {
  return {
    id: `multi_select.${op}.${tag.id}`,
    label: tag.name,
    section: 'organize',
    handler: async ({ target }) => {
      const t = asMulti(target);
      if (!t) return;
      await api.bulkSessions({ op, ids: [...t.ids], payload: { tag_id: tag.id } });
      sessionSelection.clear();
      await sessions.refresh(sessions.filter);
    },
  };
}

export const MULTI_SELECT_ACTIONS: readonly Action[] = [
  {
    id: 'multi_select.clear',
    label: 'Clear selection',
    section: 'navigate',
    mnemonic: 'c',
    handler: () => {
      sessionSelection.clear();
    },
  },
  {
    id: 'multi_select.tag',
    label: 'Add tag ▸',
    section: 'organize',
    mnemonic: 't',
    handler: () => {},
    submenu: () => tags.list.map((tag) => tagSubmenuItem(tag, 'tag')),
  },
  {
    id: 'multi_select.untag',
    label: 'Remove tag ▸',
    section: 'organize',
    advanced: true,
    handler: () => {},
    submenu: () => tags.list.map((tag) => tagSubmenuItem(tag, 'untag')),
  },
  {
    id: 'multi_select.close',
    label: 'Close sessions',
    section: 'organize',
    mnemonic: 'l',
    handler: async ({ target }) => {
      const t = asMulti(target);
      if (!t) return;
      await api.bulkSessions({ op: 'close', ids: [...t.ids] });
      sessionSelection.clear();
      await sessions.refresh(sessions.filter);
    },
  },
  {
    id: 'multi_select.export',
    label: 'Export as JSON',
    section: 'copy',
    mnemonic: 'e',
    handler: async ({ target }) => {
      const t = asMulti(target);
      if (!t) return;
      const result = await api.bulkSessions({ op: 'export', ids: [...t.ids] });
      if (result.op !== 'export') return;
      const blob = new Blob([JSON.stringify(result, null, 2)], {
        type: 'application/json',
      });
      const stamp = new Date().toISOString().replace(/[:.]/g, '-');
      downloadBlob(blob, `bearings-sessions-${stamp}.json`);
    },
  },
  {
    id: 'multi_select.delete',
    label: 'Delete sessions',
    section: 'destructive',
    destructive: true,
    mnemonic: 'd',
    handler: ({ target }) => {
      const t = asMulti(target);
      if (!t) return;
      const count = t.ids.length;
      const noun = count === 1 ? 'session' : 'sessions';
      confirmStore.request({
        actionId: 'multi_select.delete',
        targetType: 'multi_select',
        message: `Delete ${count} ${noun}? This cannot be undone. Message history and tool calls will be wiped.`,
        confirmLabel: 'Delete',
        destructive: true,
        onConfirm: async () => {
          await api.bulkSessions({ op: 'delete', ids: [...t.ids] });
          sessionSelection.clear();
          await sessions.refresh(sessions.filter);
        },
      });
    },
  },
];
