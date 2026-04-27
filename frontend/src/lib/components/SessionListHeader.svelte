<script lang="ts">
  /**
   * Sidebar header strip — title + action buttons. Extracted from
   * `SessionList.svelte` (§FileSize). All state stays in the parent;
   * this component only renders + dispatches.
   */
  import { uiActions } from '$lib/stores/ui_actions.svelte';
  import PendingOpsBadge from '$lib/components/pending/PendingOpsBadge.svelte';
  import TemplatePicker from '$lib/components/TemplatePicker.svelte';

  interface Props {
    onImportClick: () => void;
    onSettingsClick: () => void;
    onImportFileChange: (e: Event) => void;
    /** The parent owns the file-input ref so it can pass it to drag/
     * drop fallback handlers; we receive a setter so `bind:this` keeps
     * working across the boundary. */
    bindImportInput: (el: HTMLInputElement | undefined) => void;
  }

  const {
    onImportClick,
    onSettingsClick,
    onImportFileChange,
    bindImportInput
  }: Props = $props();

  let importInput: HTMLInputElement | undefined = $state();

  $effect(() => {
    bindImportInput(importInput);
  });
</script>

<div class="flex items-center justify-between gap-2">
  <h2 class="text-xs uppercase tracking-wider text-slate-400">Sessions</h2>
  <div class="flex items-center gap-1">
    <button
      type="button"
      class="text-[11px] rounded bg-slate-800 hover:bg-slate-700 px-1.5 py-0.5"
      aria-label="Import session from JSON"
      title="Import a session.json file"
      onclick={onImportClick}
    >
      ⇡
    </button>
    <input
      type="file"
      accept="application/json,.json"
      multiple
      class="hidden"
      bind:this={importInput}
      onchange={onImportFileChange}
    />
    <PendingOpsBadge />
    <TemplatePicker />
    <a
      href="/vault"
      class="text-[11px] rounded bg-slate-800 hover:bg-slate-700 px-1.5 py-0.5"
      aria-label="Open vault (plans + TODOs)"
      title="Open vault — browse plans and TODO.md files"
      data-testid="vault-link"
    >
      📚
    </a>
    <button
      type="button"
      class="text-[11px] rounded bg-slate-800 hover:bg-slate-700 px-1.5 py-0.5"
      aria-label="Open settings"
      onclick={onSettingsClick}
    >
      ⚙
    </button>
    <button
      type="button"
      class="text-[11px] rounded bg-slate-800 hover:bg-slate-700 px-1.5 py-0.5"
      onclick={() => uiActions.toggleNewSession()}
      aria-label="Toggle new session form"
    >
      {uiActions.newSessionOpen ? 'Cancel' : '+ New'}
    </button>
  </div>
</div>
