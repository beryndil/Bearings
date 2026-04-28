<script lang="ts">
  /** Destructive-action row. Visual: rose-tinted button on the right.
   * Behavioural: routes through the existing `confirmStore` so the
   * confirmation modal looks identical to every other destructive
   * confirm in Bearings — same fonts, same Esc-to-dismiss, same
   * "don't ask again this session" affordance.
   *
   * `onConfirm` runs only after the user accepts the confirm dialog.
   * Any thrown error surfaces as a row-level error pill. No inline
   * destructive toggles — every danger action goes through confirm.
   */
  import SettingsRow, { type SaveState } from './SettingsRow.svelte';
  import { confirmStore } from '$lib/context-menu/confirm.svelte';

  interface Props {
    title: string;
    description?: string;
    /** Button label, e.g. "Sign out" or "Delete history". */
    actionLabel: string;
    /** Confirmation prompt shown in the modal. */
    confirmMessage: string;
    /** Stable id passed to confirmStore for "don't ask again". */
    actionId: string;
    /** Target type for confirm-store suppression scoping. Settings
     * danger actions don't have a natural target like "session" or
     * "message", so we fix this to "settings" — every danger row
     * shares one suppression scope, but a different `actionId` keeps
     * each row independent. */
    targetType?: string;
    /** Fired after the user accepts the confirm. Throw to error. */
    onConfirm: () => Promise<void> | void;
    disabled?: boolean;
  }

  let {
    title,
    description,
    actionLabel,
    confirmMessage,
    actionId,
    targetType = 'settings',
    onConfirm,
    disabled = false,
  }: Props = $props();

  let saveState = $state<SaveState>({ kind: 'idle' });

  async function fire(): Promise<void> {
    if (disabled) return;
    // The confirm store owns the handler — we hand it our async
    // work, and it runs only after the user accepts. The outer
    // `request()` resolves whether or not the user accepted, so we
    // track state inside the inner handler, not after the await.
    await confirmStore.request({
      actionId,
      targetType,
      message: confirmMessage,
      destructive: true,
      confirmLabel: actionLabel,
      onConfirm: async () => {
        saveState = { kind: 'saving' };
        try {
          await onConfirm();
          saveState = { kind: 'saved' };
          setTimeout(() => {
            saveState = { kind: 'idle' };
          }, 1500);
        } catch (err) {
          saveState = {
            kind: 'error',
            message: err instanceof Error ? err.message : String(err),
          };
          throw err;
        }
      },
    });
  }
</script>

<SettingsRow {title} {description} state={saveState}>
  {#snippet control()}
    <button
      type="button"
      class="rounded bg-rose-700/80 px-3 py-1.5 text-sm
        font-medium text-white hover:bg-rose-600 focus:outline-none focus:ring-2
        focus:ring-rose-500/60 focus:ring-offset-1 focus:ring-offset-slate-900 disabled:cursor-not-allowed
        disabled:opacity-50"
      {disabled}
      onclick={fire}
      data-testid="settings-danger-button"
    >
      {actionLabel}
    </button>
  {/snippet}
</SettingsRow>
