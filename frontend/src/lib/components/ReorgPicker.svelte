<script lang="ts">
  /**
   * Session-picker host for the reorg flows (move / split / merge,
   * bulk variants).
   *
   * Owns: the picker's open state, the active op + anchor + bulk-id
   * snapshot, and the `reorgStore` bridge that listens for per-message
   * ⋯-menu requests dispatched by `actions/message.ts`. Parents drive
   * the picker via the `bind:this` exports below — `openMove(msg)`,
   * `openSplit(msg)`, `openBulkMove(ids)`, `openBulkSplit(ids)`,
   * `openMerge()` — and supply a `controller` to handle the actual
   * mutations on confirm.
   *
   * Lives outside `Conversation.svelte` so the parent shrinks under
   * the project's 400-line cap. The picker template (modal +
   * confirmation labels) and its trigger handlers all moved here as
   * one cohesive unit. The mutation flows themselves (do*,
   * pickerPick*, createEmptySession, undo) live in
   * `reorg-actions.svelte.ts` and are invoked here on confirm.
   */
  import { reorgStore } from '$lib/context-menu/reorg.svelte';
  import { conversation } from '$lib/stores/conversation.svelte';
  import { sessions } from '$lib/stores/sessions.svelte';
  import * as api from '$lib/api';
  import { pickerConfirmLabel, pickerTitle, type PickerOp } from '$lib/utils/reorg-picker';
  import type { ReorgController } from '$lib/utils/reorg-actions.svelte';
  import SessionPickerModal from './SessionPickerModal.svelte';

  /** Imperative surface exposed via `bind:this` so the parent can
   * trigger pickers from header buttons / bulk action bar without
   * each call site duplicating the open* boilerplate. */
  export type ReorgPickerHandle = {
    openMove: (msg: api.Message) => void;
    openSplit: (msg: api.Message) => void;
    openBulkMove: (ids: string[]) => void;
    openBulkSplit: (ids: string[]) => void;
    openMerge: () => void;
  };

  let {
    controller,
  }: {
    controller: ReorgController;
  } = $props();

  // Slice 3: Session Reorg — Move + Split ops driven from the per-
  // message ⋯ menu. `pickerOp` flips the picker's confirm label; the
  // anchor is the message the menu was opened from. Slice 4 added the
  // bulk variants: `bulk-move` moves the current selection to an
  // existing or new target, `bulk-split` moves the selection into a
  // fresh session (picker opens on the create form). Slice 5 added
  // `merge`: folds the entire source into an existing target (no
  // create-new path, no per-message anchor).
  let pickerOpen = $state(false);
  let pickerOp = $state<PickerOp>('move');
  let pickerAnchor = $state<api.Message | null>(null);
  // Snapshot of the ids at picker-open for bulk ops — keeps the op
  // stable if the user happens to tweak the selection after opening.
  let pickerBulkIds = $state<string[]>([]);

  /** Imperative open — dispatched from the per-message ⋯ menu (Move
   * Message). Exported for parent `bind:this` usage. */
  export function openMove(msg: api.Message): void {
    pickerOp = 'move';
    pickerAnchor = msg;
    pickerBulkIds = [];
    pickerOpen = true;
  }

  /** Imperative open — dispatched from the per-message ⋯ menu (Split
   * After). Exported for parent `bind:this` usage. */
  export function openSplit(msg: api.Message): void {
    pickerOp = 'split';
    pickerAnchor = msg;
    pickerBulkIds = [];
    pickerOpen = true;
  }

  /** Imperative open — dispatched from the bulk action bar (Move
   * Selected). Caller passes a snapshot of currently-selected ids so
   * the op stays stable across modal interaction. */
  export function openBulkMove(ids: string[]): void {
    if (ids.length === 0) return;
    pickerOp = 'bulk-move';
    pickerAnchor = null;
    pickerBulkIds = [...ids];
    pickerOpen = true;
  }

  /** Imperative open — dispatched from the bulk action bar (Split
   * Selected). Picker opens on the create-new form by default since
   * "split selected into a new session" is the canonical case. */
  export function openBulkSplit(ids: string[]): void {
    if (ids.length === 0) return;
    pickerOp = 'bulk-split';
    pickerAnchor = null;
    pickerBulkIds = [...ids];
    pickerOpen = true;
  }

  /** Imperative open — dispatched from the header's ⇲ button. Folds
   * the entire source into another existing session. No create-new
   * path, no per-message anchor. */
  export function openMerge(): void {
    pickerOp = 'merge';
    pickerAnchor = null;
    pickerBulkIds = [];
    pickerOpen = true;
  }

  function closePicker(): void {
    pickerOpen = false;
    pickerAnchor = null;
    pickerBulkIds = [];
  }

  // Phase 5 bridge: `actions/message.ts` publishes move/split requests
  // to `reorgStore`; this effect picks them up and opens the picker for
  // the active session. Requests for other sessions are ignored — if
  // the user right-clicks a message in a background tab (e.g. via the
  // palette while on a different session), the Conversation mounted
  // against that session handles it, not this one.
  $effect(() => {
    const req = reorgStore.pending;
    if (!req) return;
    if (req.sessionId !== sessions.selectedId) return;
    const msg = conversation.messages.find((m) => m.id === req.messageId);
    if (!msg) return;
    reorgStore.clear();
    if (req.kind === 'move') openMove(msg);
    else openSplit(msg);
  });

  /** Snapshot the active op context so the controller doesn't depend
   * on this component's reactive state — keeps the contract narrow. */
  function ctx() {
    return { op: pickerOp, anchor: pickerAnchor, bulkIds: pickerBulkIds };
  }

  async function onPickExisting(targetId: string): Promise<void> {
    const snapshot = ctx();
    closePicker();
    await controller.pickerPickExisting(targetId, snapshot);
  }

  async function onPickNew(draft: { title: string; tag_ids: number[] }): Promise<void> {
    const snapshot = ctx();
    closePicker();
    await controller.pickerPickNew(draft, snapshot);
  }
</script>

<SessionPickerModal
  open={pickerOpen}
  excludeIds={sessions.selectedId ? [sessions.selectedId] : []}
  title={pickerTitle(pickerOp, pickerBulkIds.length)}
  confirmLabel={pickerConfirmLabel(pickerOp)}
  defaultCreating={pickerOp === 'bulk-split'}
  allowCreate={pickerOp !== 'merge'}
  {onPickExisting}
  {onPickNew}
  onCancel={closePicker}
/>
