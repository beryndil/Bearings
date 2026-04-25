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
    description: op.description
  });

  function ageLabel(iso: string): string {
    const started = Date.parse(iso);
    if (Number.isNaN(started)) return '';
    const seconds = Math.floor((Date.now() - started) / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    if (hours < 48) return `${hours}h`;
    const days = Math.floor(hours / 24);
    return `${days}d`;
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<li
  class="flex items-start gap-2 rounded border border-slate-800 bg-slate-950/60
    px-2 py-1.5 hover:border-slate-700"
  use:contextmenu={{ target }}
  data-testid="pending-op-row"
>
  <div class="flex-1 min-w-0">
    <div class="flex items-baseline gap-2">
      <span class="text-xs font-medium text-slate-100 truncate">{op.name}</span>
      <span class="text-[10px] text-slate-500">{ageLabel(op.started)}</span>
    </div>
    {#if op.description}
      <p class="text-[11px] text-slate-400 line-clamp-2">{op.description}</p>
    {/if}
    {#if op.command}
      <code class="text-[10px] text-slate-500 font-mono truncate block">
        $ {op.command}
      </code>
    {/if}
  </div>
  <button
    type="button"
    class="text-[10px] rounded bg-emerald-700/60 hover:bg-emerald-600 px-1.5 py-0.5
      text-emerald-100"
    onclick={() => void pending.resolve(directory, op.name)}
    title="Mark resolved"
    data-testid="pending-op-resolve"
  >
    ✓
  </button>
  <button
    type="button"
    class="text-[10px] rounded bg-slate-800 hover:bg-rose-700/70 px-1.5 py-0.5
      text-slate-300 hover:text-rose-100"
    onclick={() => void pending.dismiss(directory, op.name)}
    title="Dismiss"
    data-testid="pending-op-dismiss"
  >
    ✕
  </button>
</li>
