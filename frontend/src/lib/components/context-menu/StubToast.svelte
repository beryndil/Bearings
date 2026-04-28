<script lang="ts">
  import { stubStore, type StubItem } from '$lib/context-menu/stub.svelte';

  // Single stub-toast row. Stores a generated "actionId" tag + reason
  // for the "not yet implemented" signal. Unlike UndoToast there is
  // no interactive button — these are advisory, so dismissal is
  // purely an × or the auto-timeout owned by the store.

  type Props = {
    item: StubItem;
  };

  const { item }: Props = $props();
</script>

<div
  class="pointer-events-auto flex max-w-sm items-center gap-3 rounded-lg border
    border-slate-700 bg-slate-900 px-4 py-3 shadow-2xl"
  role="status"
  aria-live="polite"
  data-testid="stub-toast"
  data-action-id={item.actionId}
>
  <span
    class="rounded border border-amber-500/30 bg-amber-500/10 px-1.5
      py-0.5 font-mono text-[10px] uppercase tracking-wider text-amber-400"
  >
    Stub
  </span>
  <span class="flex-1 text-xs text-slate-200">
    {item.reason ?? `Not yet implemented: ${item.actionId}`}
  </span>
  <button
    type="button"
    class="text-xs text-slate-500 hover:text-slate-300"
    aria-label="Dismiss stub toast"
    onclick={() => stubStore.dismiss(item.id)}
  >
    ✕
  </button>
</div>
