<script lang="ts">
  import * as api from '$lib/api';
  import { sessions } from '$lib/stores/sessions.svelte';
  import { tags } from '$lib/stores/tags.svelte';

  // Slice 3 of the Session Reorg plan
  // (`~/.claude/plans/sparkling-triaging-otter.md`). A modal that lets
  // the user pick an existing session as the target of a reorg op — or
  // spin up a new session inline with just title + tags (the rest of
  // the row inherits from the source at the parent's discretion).
  //
  // Two callback variants:
  //   - onPickExisting(sessionId)  — chose a row from the candidate list
  //   - onPickNew({ title, tag_ids }) — filled in the inline create form
  // The modal doesn't close itself; the parent decides whether the
  // backend call succeeded before dismissing.

  export type NewSessionDraft = {
    title: string;
    tag_ids: number[];
  };

  type Props = {
    open: boolean;
    /** Sessions to hide from the picker — always at least the source
     * session of the pending move (moving to yourself is a no-op the
     * backend rejects anyway). */
    excludeIds?: string[];
    /** Label on the confirm button + modal title. Overridable so the
     * same picker drops cleanly into Merge flows in a later slice. */
    confirmLabel?: string;
    title?: string;
    /** `true` (default) shows the "create new session" affordance.
     * Disable when the flow only makes sense against an existing
     * target (e.g. eventual Merge op). */
    allowCreate?: boolean;
    onPickExisting: (sessionId: string) => void;
    onPickNew?: (draft: NewSessionDraft) => void;
    onCancel: () => void;
  };

  const {
    open,
    excludeIds = [],
    confirmLabel = 'Move here',
    title = 'Move messages to…',
    allowCreate = true,
    onPickExisting,
    onPickNew,
    onCancel
  }: Props = $props();

  let query = $state('');
  let highlighted = $state<string | null>(null);
  let filterTagIds = $state<number[]>([]);
  let creating = $state(false);
  let newTitle = $state('');
  let newTagIds = $state<number[]>([]);
  let createError = $state<string | null>(null);

  // Reset state whenever the modal opens — otherwise a cancelled draft
  // would persist across invocations.
  $effect(() => {
    if (!open) return;
    query = '';
    highlighted = null;
    filterTagIds = [];
    creating = false;
    newTitle = '';
    newTagIds = [];
    createError = null;
  });

  const excludeSet = $derived(new Set(excludeIds));
  const queryLower = $derived(query.trim().toLowerCase());

  // Cache session→tag-id lookups so filter toggles don't re-hit the
  // network. Populated lazily on first tag-filter use.
  let sessionTagsById = $state<Record<string, number[]>>({});

  async function ensureSessionTags(id: string): Promise<void> {
    if (sessionTagsById[id]) return;
    try {
      const list = await api.listSessionTags(id);
      sessionTagsById = { ...sessionTagsById, [id]: list.map((t) => t.id) };
    } catch {
      // Filter is a convenience — a failed lookup just excludes the
      // row rather than blocking the whole picker.
      sessionTagsById = { ...sessionTagsById, [id]: [] };
    }
  }

  $effect(() => {
    if (!open || filterTagIds.length === 0) return;
    for (const s of sessions.list) {
      if (!sessionTagsById[s.id]) void ensureSessionTags(s.id);
    }
  });

  function matchesFilter(s: api.Session): boolean {
    if (filterTagIds.length === 0) return true;
    const ids = sessionTagsById[s.id];
    if (!ids) return false;
    return filterTagIds.every((t) => ids.includes(t));
  }

  const candidates = $derived(
    sessions.list
      .filter((s) => !excludeSet.has(s.id))
      .filter((s) => {
        if (queryLower === '') return true;
        const hay = `${s.title ?? ''} ${s.working_dir} ${s.model}`.toLowerCase();
        return hay.includes(queryLower);
      })
      .filter(matchesFilter)
  );

  // Keep the keyboard highlight on a valid row as the list narrows.
  $effect(() => {
    if (!highlighted) return;
    if (!candidates.some((s) => s.id === highlighted)) {
      highlighted = candidates[0]?.id ?? null;
    }
  });

  function toggleFilterTag(id: number) {
    filterTagIds = filterTagIds.includes(id)
      ? filterTagIds.filter((x) => x !== id)
      : [...filterTagIds, id];
  }

  function toggleNewTag(id: number) {
    newTagIds = newTagIds.includes(id)
      ? newTagIds.filter((x) => x !== id)
      : [...newTagIds, id];
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.preventDefault();
      onCancel();
      return;
    }
    if (creating) return;
    if (candidates.length === 0) return;
    const idx = candidates.findIndex((s) => s.id === highlighted);
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const next = idx < 0 ? 0 : Math.min(idx + 1, candidates.length - 1);
      highlighted = candidates[next].id;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const next = idx < 0 ? candidates.length - 1 : Math.max(idx - 1, 0);
      highlighted = candidates[next].id;
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const pick = highlighted ?? candidates[0]?.id ?? null;
      if (pick) onPickExisting(pick);
    }
  }

  function submitNew() {
    createError = null;
    const t = newTitle.trim();
    if (t === '') {
      createError = 'Title required for the new session.';
      return;
    }
    if (newTagIds.length === 0) {
      createError = 'Attach at least one tag.';
      return;
    }
    onPickNew?.({ title: t, tag_ids: [...newTagIds] });
  }
</script>

{#if open}
  <div
    class="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/80 p-4"
    role="dialog"
    aria-modal="true"
    aria-label={title}
    onkeydown={onKeydown}
    tabindex="-1"
    data-testid="session-picker"
  >
    <div
      class="w-full max-w-lg rounded-lg border border-slate-800 bg-slate-900 p-5 shadow-2xl
        flex flex-col gap-3"
    >
      <header class="flex items-start justify-between">
        <h2 class="text-sm font-medium text-slate-200">{title}</h2>
        <button
          type="button"
          class="text-slate-500 hover:text-slate-300 text-sm"
          aria-label="Close picker"
          onclick={onCancel}
        >
          ✕
        </button>
      </header>

      {#if !creating}
        <input
          type="text"
          class="rounded bg-slate-950 border border-slate-800 px-2 py-2 text-sm
            focus:outline-none focus:border-slate-600"
          placeholder="Search by title, working dir, or model…"
          aria-label="Search sessions"
          bind:value={query}
          data-testid="picker-search"
        />

        {#if tags.list.length > 0}
          <div class="flex flex-wrap gap-1" aria-label="Filter by tag">
            {#each tags.list as tag (tag.id)}
              {@const active = filterTagIds.includes(tag.id)}
              <button
                type="button"
                class="rounded px-2 py-0.5 text-[11px] font-mono border
                  {active
                    ? 'bg-emerald-700 border-emerald-500 text-white'
                    : 'bg-slate-900 border-slate-800 hover:border-slate-600 text-slate-300'}"
                aria-pressed={active}
                onclick={() => toggleFilterTag(tag.id)}
              >
                {#if tag.pinned}<span class="text-amber-300">★</span>{/if}
                {tag.name}
              </button>
            {/each}
          </div>
        {/if}

        <ul
          class="max-h-72 overflow-y-auto rounded border border-slate-800"
          aria-label="Session candidates"
          data-testid="picker-list"
        >
          {#if candidates.length === 0}
            <li class="px-3 py-2 text-xs text-slate-600">
              No sessions match. Clear the filter or create a new one below.
            </li>
          {:else}
            {#each candidates as s (s.id)}
              {@const hi = highlighted === s.id}
              <li>
                <button
                  type="button"
                  class="w-full text-left px-3 py-2 border-b border-slate-800 last:border-b-0
                    hover:bg-slate-800 {hi ? 'bg-slate-800' : ''}"
                  onclick={() => onPickExisting(s.id)}
                  onmouseenter={() => (highlighted = s.id)}
                  data-testid="picker-row"
                  data-session-id={s.id}
                >
                  <div class="text-sm text-slate-200 truncate">
                    {s.title ?? '(untitled)'}
                  </div>
                  <div class="text-[10px] text-slate-500 font-mono truncate">
                    {s.model} · {s.working_dir} · {s.message_count} msg{s.message_count === 1
                      ? ''
                      : 's'}
                  </div>
                </button>
              </li>
            {/each}
          {/if}
        </ul>

        {#if allowCreate && onPickNew}
          <button
            type="button"
            class="self-start text-xs text-emerald-400 hover:text-emerald-300"
            onclick={() => (creating = true)}
            data-testid="picker-create-toggle"
          >
            + Create a new session for this instead…
          </button>
        {/if}

        <div class="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            class="rounded bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs"
            onclick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            class="rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-1.5 text-xs
              disabled:opacity-50"
            disabled={candidates.length === 0}
            onclick={() => {
              const pick = highlighted ?? candidates[0]?.id ?? null;
              if (pick) onPickExisting(pick);
            }}
            data-testid="picker-confirm"
          >
            {confirmLabel}
          </button>
        </div>
      {:else}
        <section class="flex flex-col gap-2" aria-label="Create new session">
          <p class="text-[11px] text-slate-500">
            Other fields (model, working dir) inherit from the source session.
          </p>
          <label class="flex flex-col text-xs gap-1">
            <span class="text-slate-400">Title</span>
            <input
              type="text"
              class="rounded bg-slate-950 border border-slate-800 px-2 py-2 text-sm
                focus:outline-none focus:border-slate-600"
              placeholder="Short title for the new session"
              bind:value={newTitle}
              data-testid="picker-new-title"
            />
          </label>
          {#if tags.list.length > 0}
            <div class="flex flex-col text-xs gap-1">
              <span class="text-slate-400">Tags <span class="text-rose-400">*</span></span>
              <div class="flex flex-wrap gap-1">
                {#each tags.list as tag (tag.id)}
                  {@const active = newTagIds.includes(tag.id)}
                  <button
                    type="button"
                    class="rounded px-2 py-0.5 text-[11px] font-mono border
                      {active
                        ? 'bg-emerald-700 border-emerald-500 text-white'
                        : 'bg-slate-900 border-slate-800 hover:border-slate-600 text-slate-300'}"
                    aria-pressed={active}
                    onclick={() => toggleNewTag(tag.id)}
                  >
                    {#if tag.pinned}<span class="text-amber-300">★</span>{/if}
                    {tag.name}
                  </button>
                {/each}
              </div>
            </div>
          {:else}
            <p class="text-[11px] text-rose-400">
              Create a tag first — sessions must be tagged.
            </p>
          {/if}
          {#if createError}
            <p class="text-xs text-rose-400" role="alert">{createError}</p>
          {/if}
          <div class="flex items-center justify-end gap-2 pt-1">
            <button
              type="button"
              class="rounded bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs"
              onclick={() => (creating = false)}
            >
              Back
            </button>
            <button
              type="button"
              class="rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-1.5 text-xs
                disabled:opacity-50"
              disabled={tags.list.length === 0}
              onclick={submitNew}
              data-testid="picker-new-confirm"
            >
              {confirmLabel}
            </button>
          </div>
        </section>
      {/if}
    </div>
  </div>
{/if}
