<script lang="ts">
  import * as api from '$lib/api';
  import { tags } from '$lib/stores/tags.svelte';
  import { renderMarkdown } from '$lib/render';
  import FolderPicker from './FolderPicker.svelte';
  import ModelSelect from './ModelSelect.svelte';

  let {
    open = $bindable(false),
    tagId = null as number | null,
  }: { open?: boolean; tagId?: number | null } = $props();

  let name = $state('');
  let pinned = $state(false);
  let sortOrder = $state(0);
  let defaultWorkingDir = $state('');
  let defaultModel = $state('');
  /** Tag tint. Null = dim-slate fallback used by SeverityShield /
   * TagIcon. Any hex string becomes the medallion fill. Exposed in
   * the modal so severity rows (Blocker etc.) can be re-themed to
   * match Daisy's palette preferences without a DB poke. */
  let color = $state<string | null>(null);
  let memory = $state('');
  /** Tracks the memory content as it existed when the modal opened, so
   * save-time we can tell the difference between "user left it blank
   * because there was no memory" (do nothing) and "user cleared an
   * existing memory" (DELETE). */
  let originalMemory = $state<string | null>(null);
  let showPreview = $state(false);
  let saving = $state(false);
  let loadError = $state<string | null>(null);
  let saveError = $state<string | null>(null);
  let confirmDelete = $state(false);

  const current = $derived(tagId === null ? null : (tags.list.find((t) => t.id === tagId) ?? null));

  /** Preset swatches for the color row. The first five mirror the
   * migration-0021 severity ramp (red → emerald) so a severity tag is
   * one click from its canonical color after an accidental override.
   * The rest are Tailwind-500-ish neutrals that pair well with both
   * the dark sidebar and the shield bevel highlight. Kept as a const
   * rather than fetched because the picker is cheap render and the
   * palette isn't user-editable. */
  const PALETTE = [
    '#dc2626', // red-600 — Blocker
    '#ea580c', // orange-600 — Critical
    '#f59e0b', // amber-500 — Medium
    '#84cc16', // lime-500 — Low
    '#10b981', // emerald-500 — Quality of Life
    '#06b6d4', // cyan-500
    '#3b82f6', // blue-500
    '#6366f1', // indigo-500
    '#8b5cf6', // violet-500
    '#ec4899', // pink-500
    '#a3a3a3', // neutral-400
    '#475569', // slate-600 — matches the fallback
  ] as const;

  async function loadMemory(id: number): Promise<void> {
    loadError = null;
    try {
      const mem = await api.getTagMemory(id);
      memory = mem.content;
      originalMemory = mem.content;
    } catch (err) {
      // 404 is expected — tag has no memory yet. Anything else is a
      // real error worth surfacing.
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('404')) {
        memory = '';
        originalMemory = null;
      } else {
        loadError = msg;
      }
    }
  }

  /** Tracks whether we've already hydrated state for the current open
   * cycle. Without this, `tags.refresh()` (which happens after save)
   * gives `current` a new object reference, retriggers the effect,
   * and wipes any in-flight user edits. Reset to null when the modal
   * closes so the next open re-hydrates cleanly. */
  let hydratedFor = $state<number | null>(null);

  $effect(() => {
    if (!open) {
      hydratedFor = null;
      return;
    }
    if (!current || hydratedFor === current.id) return;
    hydratedFor = current.id;
    name = current.name;
    pinned = current.pinned;
    sortOrder = current.sort_order;
    defaultWorkingDir = current.default_working_dir ?? '';
    defaultModel = current.default_model ?? '';
    color = current.color;
    memory = '';
    originalMemory = null;
    showPreview = false;
    saveError = null;
    confirmDelete = false;
    loadMemory(current.id);
  });

  function blankToNull(v: string): string | null {
    const trimmed = v.trim();
    return trimmed === '' ? null : trimmed;
  }

  async function onSave() {
    if (tagId === null) return;
    const trimmedName = name.trim();
    if (trimmedName === '') return;
    saving = true;
    saveError = null;
    try {
      await tags.update(tagId, {
        name: trimmedName,
        color,
        pinned,
        sort_order: sortOrder,
        default_working_dir: blankToNull(defaultWorkingDir),
        default_model: blankToNull(defaultModel),
      });
      const memoryTrimmed = memory.trim();
      if (memoryTrimmed === '' && originalMemory !== null) {
        // Had a memory, user cleared it → delete.
        await api.deleteTagMemory(tagId);
      } else if (memoryTrimmed !== '') {
        // Has content → upsert. Store the raw (untrimmed) so leading
        // whitespace in prose is preserved.
        await api.putTagMemory(tagId, memory);
      }
    } catch (err) {
      saveError = err instanceof Error ? err.message : String(err);
      saving = false;
      return;
    }
    saving = false;
    open = false;
  }

  async function onDelete() {
    if (tagId === null) return;
    if (!confirmDelete) {
      confirmDelete = true;
      return;
    }
    saving = true;
    await tags.remove(tagId);
    saving = false;
    open = false;
  }

  function onCancel() {
    open = false;
  }

  const previewHtml = $derived(memory.trim() === '' ? '' : renderMarkdown(memory));
</script>

{#if open && current}
  <div class="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/80 p-4">
    <form
      class="flex max-h-[90vh] w-full max-w-2xl flex-col gap-4 overflow-y-auto rounded-lg
        border border-slate-800 bg-slate-900 p-6 shadow-2xl"
      onsubmit={(e) => {
        e.preventDefault();
        onSave();
      }}
    >
      <header class="flex items-start justify-between">
        <div>
          <h2 class="text-lg font-medium">Edit tag</h2>
          <p class="mt-1 font-mono text-[10px] text-slate-600">
            <!-- Mirror the sidebar split so the edit modal's headline
                 count matches the row Daisy just clicked on. -->
            <span class={current.open_session_count > 0 ? 'text-emerald-400' : ''}>
              {current.open_session_count}
            </span>
            {current.session_count} session{current.session_count === 1 ? '' : 's'}
          </p>
        </div>
        <button
          type="button"
          class="text-sm text-slate-500 hover:text-slate-300"
          aria-label="Close edit"
          onclick={onCancel}
        >
          ✕
        </button>
      </header>

      <div class="grid grid-cols-[1fr_auto_auto] items-end gap-3">
        <label class="flex flex-col gap-1 text-xs">
          <span class="text-slate-400">Name *</span>
          <input
            type="text"
            required
            class="rounded border border-slate-800 bg-slate-950 px-2 py-2 text-sm
              focus:border-slate-600 focus:outline-none"
            bind:value={name}
          />
        </label>
        <label class="flex flex-col gap-1 text-xs">
          <span class="text-slate-400">Order</span>
          <input
            type="number"
            class="w-16 rounded border border-slate-800 bg-slate-950 px-2 py-2 font-mono text-sm
              focus:border-slate-600 focus:outline-none"
            title="Lower number = higher in sidebar. Breaks ties in prompt assembly (later wins)."
            bind:value={sortOrder}
          />
        </label>
        <label class="inline-flex items-center gap-1.5 pb-2 text-xs text-slate-300">
          <input type="checkbox" bind:checked={pinned} class="accent-emerald-500" />
          <span>Pinned</span>
        </label>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div class="flex flex-col gap-1 text-xs">
          <span class="text-slate-400">Default working dir</span>
          <FolderPicker bind:value={defaultWorkingDir} />
        </div>
        <div class="flex flex-col gap-1 text-xs">
          <span class="text-slate-400">Default model</span>
          <ModelSelect bind:value={defaultModel} />
        </div>
      </div>

      <!-- Color picker. Drives the sidebar medallion tint — the
           SeverityShield on severity rows, the luggage-tag TagIcon
           on general rows. Null color (✕) falls back to the dim
           slate used for the "no severity" / "no color chosen" look. -->
      <section class="flex flex-col gap-1.5">
        <div class="flex items-baseline justify-between">
          <span class="text-xs text-slate-400">Color</span>
          <span class="font-mono text-[10px] text-slate-600">
            {color ?? 'none — falls back to slate'}
          </span>
        </div>
        <div class="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            class="flex h-6 w-6 items-center justify-center rounded-full border text-[10px]
              text-slate-300 hover:border-slate-400 {color === null
              ? 'border-emerald-400 bg-slate-800 ring-1 ring-emerald-400/60'
              : 'border-slate-700 bg-slate-900'}"
            onclick={() => (color = null)}
            aria-label="Clear color"
            title="Clear color — medallion falls back to dim slate">✕</button
          >
          {#each PALETTE as swatch}
            <button
              type="button"
              class="h-6 w-6 rounded-full border transition-transform hover:scale-110 {color?.toLowerCase() ===
              swatch.toLowerCase()
                ? 'border-emerald-400 ring-1 ring-emerald-400/60'
                : 'border-slate-700'}"
              style="background-color: {swatch}"
              onclick={() => (color = swatch)}
              aria-label={`Use ${swatch}`}
              title={swatch}
            ></button>
          {/each}
          <!-- Native picker for anything outside the palette. Its
               value is always a hex (no null), so clearing still
               routes through the ✕ button. -->
          <label
            class="ml-1 inline-flex cursor-pointer items-center gap-1 text-[10px] text-slate-500"
            title="Pick any hex color"
          >
            <input
              type="color"
              class="h-6 w-6 cursor-pointer rounded border-0 bg-transparent"
              value={color ?? '#475569'}
              oninput={(e) => (color = (e.currentTarget as HTMLInputElement).value)}
            />
            <span>custom</span>
          </label>
        </div>
      </section>

      <section class="flex flex-col gap-1">
        <div class="flex items-baseline justify-between gap-2">
          <span class="text-xs text-slate-400">
            Memory <span class="text-slate-600"
              >(markdown — injected into every session with this tag)</span
            >
          </span>
          <button
            type="button"
            class="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase
              tracking-wider text-slate-300 hover:bg-slate-700"
            onclick={() => (showPreview = !showPreview)}
          >
            {showPreview ? 'Edit' : 'Preview'}
          </button>
        </div>
        {#if showPreview}
          <div
            class="prose prose-sm prose-invert min-h-[10rem] max-w-none rounded border
              border-slate-800 bg-slate-950 px-3 py-2 text-sm"
          >
            {#if previewHtml}
              {@html previewHtml}
            {:else}
              <span class="text-slate-600">(empty — nothing to preview)</span>
            {/if}
          </div>
        {:else}
          <textarea
            class="min-h-[10rem] resize-y rounded border border-slate-800 bg-slate-950 px-2
              py-2 font-mono text-sm focus:border-slate-600 focus:outline-none"
            rows="10"
            placeholder="# Context&#10;&#10;Directory pointers, conventions, constraints. Markdown."
            bind:value={memory}
          ></textarea>
        {/if}
        <p class="text-[10px] text-slate-500">
          If multiple tags have conflicting rules, later tags (lower in the sidebar sort order)
          override earlier ones.
        </p>
      </section>

      {#if loadError}
        <p class="text-xs text-rose-400">memory: {loadError}</p>
      {/if}
      {#if saveError}
        <p class="text-xs text-rose-400">{saveError}</p>
      {/if}
      {#if tags.error && !saveError}
        <p class="text-xs text-rose-400">{tags.error}</p>
      {/if}

      <div class="flex items-center justify-between gap-2 pt-2">
        <button
          type="button"
          class="rounded px-3 py-2 text-sm {confirmDelete
            ? 'bg-rose-600 text-white hover:bg-rose-500'
            : 'bg-slate-800 text-rose-300 hover:bg-slate-700'}"
          onclick={onDelete}
          disabled={saving}
        >
          {confirmDelete ? 'Confirm delete?' : 'Delete'}
        </button>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="rounded bg-slate-800 px-3 py-2 text-sm hover:bg-slate-700"
            onclick={onCancel}
          >
            Cancel
          </button>
          <button
            type="submit"
            class="rounded bg-emerald-600 px-3 py-2 text-sm hover:bg-emerald-500 disabled:opacity-50"
            disabled={saving || name.trim() === ''}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </form>
  </div>
{/if}
