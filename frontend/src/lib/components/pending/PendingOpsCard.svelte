<!--
  Floating pending-operations panel — Phase 16 of docs/context-menu-plan.md.
  Mounted as a singleton from +page.svelte alongside CheatSheet,
  CommandPalette, ConfirmDialog, etc. Anchored bottom-right of the
  viewport so it doesn't overlap the sidebar; dismisses on Esc /
  outside-click / dedicated close button.

  The card reads its data from the `pending` store, which already owns
  directory tracking, polling, and the open/closed flag. This component
  is a thin renderer — every mutation goes back through the store.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import PendingOpRow from './PendingOpRow.svelte';
  import { pending } from '$lib/stores/pending.svelte';

  let cardEl: HTMLElement | undefined = $state();

  function onOutsideClick(e: MouseEvent) {
    if (!pending.cardOpen) return;
    if (cardEl && !cardEl.contains(e.target as Node)) {
      pending.closeCard();
    }
  }

  onMount(() => {
    document.addEventListener('mousedown', onOutsideClick);
    return () => document.removeEventListener('mousedown', onOutsideClick);
  });
</script>

{#if pending.cardOpen}
  <!-- svelte-ignore a11y_no_noninteractive_element_to_interactive_role -->
  <aside
    bind:this={cardEl}
    class="fixed bottom-4 right-4 z-30 w-80 max-h-[60vh] flex flex-col
      rounded border border-slate-700 bg-slate-900/95 shadow-xl backdrop-blur"
    role="dialog"
    aria-label="Pending operations"
    data-testid="pending-ops-card"
  >
    <header
      class="flex items-center justify-between gap-2 border-b border-slate-800
        px-3 py-2"
    >
      <h2 class="text-xs font-semibold uppercase tracking-wider text-slate-300">
        Pending operations
      </h2>
      <div class="flex items-center gap-1">
        <button
          type="button"
          class="text-[10px] rounded bg-slate-800 hover:bg-slate-700 px-1.5 py-0.5
            text-slate-300"
          onclick={() => void pending.refresh()}
          disabled={pending.loading}
          title="Refresh"
        >
          ↻
        </button>
        <button
          type="button"
          class="text-[10px] rounded bg-slate-800 hover:bg-slate-700 px-1.5 py-0.5
            text-slate-300"
          onclick={() => pending.closeCard()}
          aria-label="Close"
          title="Close (Esc)"
        >
          ✕
        </button>
      </div>
    </header>
    <div class="flex-1 overflow-y-auto px-2 py-2">
      {#if !pending.directory}
        <p class="text-xs text-slate-500 px-2 py-3">
          Open a session to see its pending operations.
        </p>
      {:else if pending.error}
        <p class="text-xs text-rose-400 px-2 py-3">{pending.error}</p>
      {:else if pending.ops.length === 0}
        <p class="text-xs text-slate-500 px-2 py-3">
          {pending.loading ? 'Loading…' : 'No pending operations.'}
        </p>
      {:else}
        <ul class="flex flex-col gap-1.5">
          {#each pending.ops as op (op.name)}
            <PendingOpRow {op} directory={pending.directory} />
          {/each}
        </ul>
      {/if}
    </div>
    <footer
      class="border-t border-slate-800 px-3 py-1.5 text-[10px] text-slate-500"
    >
      <code>{pending.directory || '—'}</code>
    </footer>
  </aside>
{/if}
