/**
 * Message-target actions.
 *
 * Phase 1 ships `message.copy_id` only. In the final spec this item is
 * marked `[advanced]`, but during plumbing verification it stays on the
 * default menu so right-click → menu → click produces visible output.
 * It moves behind Shift when the full message menu lands in Phase 5.
 */

import type { Action } from '../types';
import { writeClipboard } from '../clipboard';

export const MESSAGE_ACTIONS: readonly Action[] = [
  {
    id: 'message.copy_id',
    label: 'Copy message ID',
    section: 'copy',
    handler: async ({ target }) => {
      if (target.type !== 'message') return;
      await writeClipboard(target.id);
    }
  }
];
