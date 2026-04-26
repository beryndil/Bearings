<script lang="ts">
  /** Settings dialog — Spyglass-parity sectioned layout.
   *
   * The previous implementation was a single-column modal with six
   * flat fields and an explicit Save/Cancel button. This one is a
   * sectioned dialog: a left nav rail over a content pane (see
   * `settings/SettingsShell.svelte`), each section composed from the
   * primitive library under `settings/`. Every row autosaves on
   * change — there is no Save button. The footer carries a
   * cross-row save indicator driven by `preferences.lastSaveStatus`
   * for the "did anything just fail to save?" question.
   *
   * Carve-outs preserved (see the section components):
   *   - Notifications: requests browser permission *before* the
   *     PATCH; throws on deny so the toggle visibly reverts.
   *   - Authentication: client-only via `prefs` store; never PATCHes
   *     /api/preferences. Per-row 'Saved' surfaces the localStorage
   *     write.
   *
   * Mounting on `open=true` causes SettingsShell to fresh-mount,
   * which in turn fresh-mounts the active section. Each section's
   * `$state()` initialiser re-seeds from the live store at that
   * moment — no `$effect`-based seeding is required (and the
   * un-tracked seeding the old code used to dodge mid-edit clobber
   * is moot under autosave because there is no defer-to-Save state
   * to clobber). */
  import { preferences } from '$lib/stores/preferences.svelte';
  import SettingsShell from './settings/SettingsShell.svelte';

  let { open = $bindable(false) }: { open?: boolean } = $props();

  function onClose(): void {
    open = false;
  }
</script>

{#if open}
  <div class="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/80 p-4">
    <div
      class="w-full max-w-3xl rounded-lg border border-slate-800 bg-slate-900 shadow-2xl
        flex flex-col"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-dialog-title"
    >
      <header
        class="flex items-start justify-between px-6 py-4 border-b border-slate-800"
      >
        <div>
          <h2 id="settings-dialog-title" class="text-lg font-medium">Settings</h2>
          <p class="text-xs text-slate-400 mt-1">
            Changes save automatically. Auth token stays on this device.
          </p>
        </div>
        <button
          type="button"
          class="text-slate-500 hover:text-slate-300 text-sm leading-none"
          aria-label="Close settings"
          onclick={onClose}
        >
          ✕
        </button>
      </header>

      <SettingsShell />

      <footer
        class="px-6 py-2 border-t border-slate-800 text-xs min-h-[2rem]
          flex items-center"
        data-testid="settings-footer"
      >
        {#if preferences.lastSaveStatus.kind === 'saving'}
          <span class="text-slate-400 italic" role="status" aria-live="polite">
            Saving…
          </span>
        {:else if preferences.lastSaveStatus.kind === 'saved'}
          <span class="text-emerald-400" role="status" aria-live="polite">
            All changes saved
          </span>
        {:else if preferences.lastSaveStatus.kind === 'error'}
          <span class="text-rose-400" role="alert">
            Failed to save: {preferences.lastSaveStatus.error}
          </span>
        {:else}
          <span class="text-slate-600">Ready.</span>
        {/if}
      </footer>
    </div>
  </div>
{/if}
