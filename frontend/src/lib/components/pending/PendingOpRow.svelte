<!--
  Single pending-operation row in the floating card. Shows name +
  description + age, plus left-click resolve and a right-click menu
  with the full `pending_operation` action set. The age is computed
  client-side off the `started` ISO string so the row updates as the
  card sits open.
-->
<script lang="ts">
  import { contextmenu } from '$lib/actions/contextmenu';
  import type { PendingOperationTarget } from '$lib/context-menu/types';
  import { pending } from '$lib/stores/pending.svelte';
  import type { PendingOperation } from '$lib/api/pending';
  import { formatRelative } from '$lib/utils/datetime';

  type Props = {
    op: PendingOperation;
    directory: string;
  };

  const { op, directory }: Props = $props();

  const target: PendingOperationTarget = $derived({
    type: 'pending_operation',
    name: op.name,
    directory,
    command: op.command,
    description: op.description,
  });

  /** Pending-op age uses the centralized `formatRelative` (§32). The
   * legacy compact form ("5m" vs. the Intl-standard "5 minutes ago")
   * is widened by ~20px in the badge but reads correctly across
   * locales — Japanese gets "5分前" rather than the locale-blind
   * "5m". Called inline in the template so each re-render of the
   * row (driven by `pending.refresh()` replacing the `ops` array
   * every 30s) picks up a fresh `Date.now()` for the delta —
   * matches the legacy `ageLabel` re-evaluation cadence. */
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<li
  class="flex items-start gap-2 rounded border border-slate-800 bg-slate-950/60
    px-2 py-1.5 hover:border-slate-700"
  use:contextmenu={{ target }}
  data-testid="pending-op-row"
>
  <div class="min-w-0 flex-1">
    <div class="flex items-baseline gap-2">
      <span class="truncate text-xs font-medium text-slate-100">{op.name}</span>
      <span class="text-[10px] text-slate-500">{formatRelative(op.started)}</span>
    </div>
    {#if op.description}
      <p class="line-clamp-2 text-[11px] text-slate-400">{op.description}</p>
    {/if}
    {#if op.command}
      <code class="block truncate font-mono text-[10px] text-slate-500">
        $ {op.command}
      </code>
    {/if}
  </div>
  <button
    type="button"
    class="rounded bg-emerald-700/60 px-1.5 py-0.5 text-[10px] text-emerald-100
      hover:bg-emerald-600"
    onclick={() => void pending.resolve(directory, op.name)}
    title="Mark resolved"
    data-testid="pending-op-resolve"
  >
    ✓
  </button>
  <button
    type="button"
    class="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300
      hover:bg-rose-700/70 hover:text-rose-100"
    onclick={() => void pending.dismiss(directory, op.name)}
    title="Dismiss"
    data-testid="pending-op-dismiss"
  >
    ✕
  </button>
</li>
