<script lang="ts">
  /**
   * Collapsible "Closed (N)" group at the bottom of the sidebar.
   * Extracted from `SessionList.svelte` (§FileSize). Rendering only —
   * the parent owns the closed-sessions list and the collapsed state.
   */
  import type { Snippet } from 'svelte';
  import type { Session } from '$lib/api';

  interface Props {
    closedList: readonly Session[];
    collapsed: boolean;
    onToggle: () => void;
    sessionRow: Snippet<[Session]>;
  }

  const { closedList, collapsed, onToggle, sessionRow }: Props = $props();
</script>

<div class="mt-2 border-t border-slate-800 pt-1">
  <button
    type="button"
    class="flex w-full items-center justify-between px-1 py-0.5 text-[11px]
      uppercase tracking-wider text-slate-400 hover:text-slate-200"
    aria-expanded={!collapsed}
    aria-controls="closed-sessions-group"
    onclick={onToggle}
    data-testid="closed-group-toggle"
  >
    <span>Closed ({closedList.length})</span>
    <span aria-hidden="true">{collapsed ? '▸' : '▾'}</span>
  </button>
  {#if !collapsed}
    <ul
      id="closed-sessions-group"
      class="mt-1 flex flex-col gap-0.5"
      data-testid="closed-sessions-list"
    >
      {#each closedList as session (session.id)}
        {@render sessionRow(session)}
      {/each}
    </ul>
  {/if}
</div>
