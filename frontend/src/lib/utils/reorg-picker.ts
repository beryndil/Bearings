/**
 * Pure label helpers for the Conversation reorg picker (move / split
 * / merge / bulk variants).
 *
 * Lives outside `Conversation.svelte` so the component shrinks and
 * the labels get a unit-test surface (`reorg-picker.test.ts`). The
 * rest of the picker subsystem (state vars, the open/close handlers,
 * the do* mutation flows, undo plumbing) stays in the component for
 * now — those mutate component-scoped `$state` runes and aren't
 * portable to a plain TS module without a meaningful Svelte 5
 * reactivity contract.
 */

export type PickerOp = 'move' | 'split' | 'bulk-move' | 'bulk-split' | 'merge';

/** Title shown at the top of the session picker modal. The bulk
 * variants embed the selection count + correct pluralisation; move
 * and split are anchored on a single message and don't need it. */
export function pickerTitle(op: PickerOp, bulkCount: number): string {
  if (op === 'split') return 'Split remaining messages into…';
  if (op === 'bulk-move') {
    return `Move ${bulkCount} selected message${bulkCount === 1 ? '' : 's'} to…`;
  }
  if (op === 'bulk-split') {
    return `Split ${bulkCount} selected message${bulkCount === 1 ? '' : 's'} into a new session`;
  }
  if (op === 'merge') return 'Merge this session into…';
  return 'Move message to…';
}

/** Action button label inside the picker. Split + bulk-split share
 * "Split here," merge gets "Merge here," everything else is the
 * canonical "Move here." */
export function pickerConfirmLabel(op: PickerOp): string {
  if (op === 'split' || op === 'bulk-split') return 'Split here';
  if (op === 'merge') return 'Merge here';
  return 'Move here';
}
