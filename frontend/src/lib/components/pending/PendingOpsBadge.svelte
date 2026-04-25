<!--
  Sidebar-header badge that surfaces the pending-ops count for the
  active project. Hidden when the count is zero (per plan §8.3 — sparse
  data, no permanent real estate cost). Click toggles the floating
  PendingOpsCard.

  Wire: mounted in SessionList.svelte's header alongside the import /
  vault / settings / new-session icons. The store owns the directory,
  the count, and the open/closed flag — this component is a thin
  display + toggle.
-->
<script lang="ts">
  import { pending } from '$lib/stores/pending.svelte';
</script>

{#if pending.count > 0}
  <button
    type="button"
    class="relative text-[11px] rounded bg-amber-900/40 hover:bg-amber-900/60
      border border-amber-700/40 px-1.5 py-0.5 text-amber-200"
    aria-label="{pending.count} pending operation{pending.count === 1 ? '' : 's'}"
    title="{pending.count} pending operation{pending.count === 1 ? '' : 's'} (Ctrl+Shift+O)"
    onclick={() => pending.toggleCard()}
    data-testid="pending-ops-badge"
  >
    ⏳ {pending.count}
  </button>
{/if}
