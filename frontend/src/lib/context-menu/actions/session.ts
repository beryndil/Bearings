/**
 * Session-target actions.
 *
 * Phase 1 ships `session.copy_id` only. It is intentionally NOT marked
 * `advanced: true` yet so the menu is visible on ordinary right-click
 * during plumbing verification. When the full session menu arrives in
 * Phase 4 — with `session.copy_share_link`, `session.archive`, and the
 * rest — `session.copy_id` moves behind Shift per the spec.
 */

import type { Action } from '../types';
import { writeClipboard } from '../clipboard';

export const SESSION_ACTIONS: readonly Action[] = [
  {
    id: 'session.copy_id',
    label: 'Copy session ID',
    section: 'copy',
    handler: async ({ target }) => {
      if (target.type !== 'session') return;
      await writeClipboard(target.id);
    }
  }
];
