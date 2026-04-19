<script lang="ts">
  import { sessions } from '$lib/stores/sessions.svelte';

  let {
    open = $bindable(false),
    sessionId
  }: { open?: boolean; sessionId: string | null } = $props();

  let title = $state('');
  let budget = $state('');
  let saving = $state(false);

  const current = $derived(
    sessionId ? (sessions.list.find((s) => s.id === sessionId) ?? null) : null
  );

  $effect(() => {
    if (open && current) {
      title = current.title ?? '';
      budget = current.max_budget_usd != null ? String(current.max_budget_usd) : '';
    }
  });

  function parseBudget(raw: string): number | null {
    const trimmed = raw.trim();
    if (trimmed === '') return null;
    const n = Number(trimmed);
    return Number.isFinite(n) && n > 0 ? n : null;
  }

  async function onSave() {
    if (!sessionId) return;
    saving = true;
    await sessions.update(sessionId, {
      title: title.trim() === '' ? null : title.trim(),
      max_budget_usd: parseBudget(budget)
    });
    saving = false;
    open = false;
  }

  function onCancel() {
    open = false;
  }
</script>

{#if open && current}
  <div class="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/80 p-4">
    <form
      class="w-full max-w-sm rounded-lg border border-slate-800 bg-slate-900 p-6 shadow-2xl
        flex flex-col gap-4"
      onsubmit={(e) => {
        e.preventDefault();
        onSave();
      }}
    >
      <header class="flex items-start justify-between">
        <div>
          <h2 class="text-lg font-medium">Edit session</h2>
          <p class="text-[10px] text-slate-600 font-mono mt-1 truncate">
            {current.model} · {current.working_dir}
          </p>
        </div>
        <button
          type="button"
          class="text-slate-500 hover:text-slate-300 text-sm"
          aria-label="Close edit"
          onclick={onCancel}
        >
          ✕
        </button>
      </header>

      <label class="flex flex-col gap-1 text-xs">
        <span class="text-slate-400">Title</span>
        <input
          type="text"
          class="rounded bg-slate-950 border border-slate-800 px-2 py-2 text-sm
            focus:outline-none focus:border-slate-600"
          placeholder="(leave empty to clear)"
          bind:value={title}
        />
      </label>

      <label class="flex flex-col gap-1 text-xs">
        <span class="text-slate-400">Budget USD</span>
        <input
          type="number"
          inputmode="decimal"
          step="0.01"
          min="0"
          placeholder="no cap"
          class="rounded bg-slate-950 border border-slate-800 px-2 py-2 text-sm font-mono
            focus:outline-none focus:border-slate-600"
          bind:value={budget}
        />
      </label>

      <div class="flex items-center justify-end gap-2 pt-2">
        <button
          type="button"
          class="rounded bg-slate-800 hover:bg-slate-700 px-3 py-2 text-sm"
          onclick={onCancel}
        >
          Cancel
        </button>
        <button
          type="submit"
          class="rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-2 text-sm
            disabled:opacity-50"
          disabled={saving}
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </form>
  </div>
{/if}
