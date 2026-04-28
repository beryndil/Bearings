/**
 * Tag and tag-chip actions — Phase 4a.2.
 *
 * Two exports in one file per the plan's §3.1 module layout:
 *   - `TAG_ACTIONS` binds to sidebar filter-panel rows in
 *     TagFilterPanel.svelte (both `general` and `severity` groups).
 *   - `TAG_CHIP_ACTIONS` binds to the chip renderings in
 *     SessionEdit.svelte and NewSessionForm.svelte. The chip carries
 *     a nullable `sessionId` because NewSessionForm renders chips for
 *     a session that hasn't been created yet — `tag_chip.detach` is
 *     hidden when `sessionId` is null.
 *
 * Real endpoints:
 *   - `tag.pin`/`tag.unpin` hit `PATCH /tags/{id}` via `tags.update`.
 *   - `tag_chip.detach` hits `DELETE /sessions/{id}/tags/{tagId}` via
 *     the API client directly (the sessions store owns the session
 *     row; tag list on the session isn't cached there, so we skip the
 *     store and let the consumer refetch its own chip list).
 *   - Edit/delete actions land as stubs for Phase 4a.3 — the existing
 *     TagEdit modal is component-local and plumbing a global opener
 *     belongs with the CommandPalette work.
 */

import * as api from '$lib/api';
import { tags } from '$lib/stores/tags.svelte';
import { writeClipboard } from '../clipboard';
import { notYetImplemented } from '../stub.svelte';
import type { Action, ContextTarget, TagChipTarget, TagTarget } from '../types';

function asTag(t: ContextTarget): TagTarget | null {
  return t.type === 'tag' ? t : null;
}

function asTagChip(t: ContextTarget): TagChipTarget | null {
  return t.type === 'tag_chip' ? t : null;
}

function lookupTag(id: number): api.Tag | null {
  return tags.list.find((t) => t.id === id) ?? null;
}

export const TAG_ACTIONS: readonly Action[] = [
  {
    id: 'tag.pin',
    label: 'Pin tag',
    section: 'organize',
    mnemonic: 'p',
    handler: async ({ target }) => {
      const t = asTag(target);
      if (!t) return;
      await tags.update(t.id, { pinned: true });
    },
    requires: (target) => {
      const t = asTag(target);
      if (!t) return false;
      const row = lookupTag(t.id);
      return row ? !row.pinned : false;
    },
  },
  {
    id: 'tag.unpin',
    label: 'Unpin tag',
    section: 'organize',
    mnemonic: 'p',
    handler: async ({ target }) => {
      const t = asTag(target);
      if (!t) return;
      await tags.update(t.id, { pinned: false });
    },
    requires: (target) => {
      const t = asTag(target);
      if (!t) return false;
      const row = lookupTag(t.id);
      return row ? row.pinned : false;
    },
  },
  {
    id: 'tag.copy_name',
    label: 'Copy tag name',
    section: 'copy',
    handler: async ({ target }) => {
      const t = asTag(target);
      if (!t) return;
      const row = lookupTag(t.id);
      if (!row) return;
      await writeClipboard(row.name);
    },
  },
  {
    id: 'tag.edit',
    label: 'Edit tag…',
    section: 'edit',
    handler: () => notYetImplemented('tag.edit'),
    disabled: () =>
      'The pencil icon on the tag row opens the editor; context-menu wiring lands in Phase 4a.3',
  },
  {
    id: 'tag.delete',
    label: 'Delete tag',
    section: 'destructive',
    destructive: true,
    advanced: true,
    handler: () => notYetImplemented('tag.delete'),
    disabled: () => 'Deleting a tag detaches it from every session — wiring lands in Phase 4a.3',
  },
];

export const TAG_CHIP_ACTIONS: readonly Action[] = [
  {
    id: 'tag_chip.copy_name',
    label: 'Copy tag name',
    section: 'copy',
    handler: async ({ target }) => {
      const t = asTagChip(target);
      if (!t) return;
      const row = lookupTag(t.tagId);
      if (!row) return;
      await writeClipboard(row.name);
    },
  },
  {
    id: 'tag_chip.detach',
    label: 'Remove tag from session',
    section: 'destructive',
    mnemonic: 'r',
    handler: async ({ target }) => {
      const t = asTagChip(target);
      if (!t || !t.sessionId) return;
      await api.detachSessionTag(t.sessionId, t.tagId);
      // The chip renderers own their own lists — SessionEdit refreshes
      // via its own effect when the session row is next touched. We
      // don't decrement tag counts here because attach/detach in
      // SessionEdit drives `tags.bumpCount` at its own callsite; a
      // context-menu detach that bypasses that path gets reconciled on
      // the next tag list refresh.
      void tags.refresh();
    },
    requires: (target) => {
      const t = asTagChip(target);
      // No session id → pre-create chip in NewSessionForm, which has
      // its own inline ✕ button; hide the context-menu detach because
      // we can't route through attach/detach without a session to
      // detach from.
      return !!(t && t.sessionId);
    },
  },
];
