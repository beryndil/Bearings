<script lang="ts">
  import { listDir, type FsEntry } from '$lib/api/fs';

  let {
    value = $bindable(''),
    placeholder = '/home/...'
  }: { value?: string; placeholder?: string } = $props();

  let open = $state(false);
  let currentPath = $state('');
  let parent = $state<string | null>(null);
  let entries = $state<FsEntry[]>([]);
  let showHidden = $state(false);
  let loading = $state(false);
  let error = $state<string | null>(null);

  async function fetchList(path: string | null): Promise<void> {
    loading = true;
    error = null;
    try {
      const result = await listDir({ path, hidden: showHidden });
      currentPath = result.path;
      parent = result.parent;
      entries = result.entries;
    } catch (e) {
      // Leave currentPath / entries untouched so the user still sees
      // the last good directory while the error is on screen.
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  async function onBrowse() {
    if (open) {
      open = false;
      return;
    }
    open = true;
    // Seed from the current text-field value, or $HOME (server-side)
    // when the field is empty.
    await fetchList(value.trim() || null);
  }

  async function descend(entry: FsEntry) {
    await fetchList(entry.path);
  }

  async function ascend() {
    if (parent !== null) await fetchList(parent);
  }

  async function toggleHidden() {
    showHidden = !showHidden;
    await fetchList(currentPath);
  }

  function useThis() {
    value = currentPath;
    open = false;
  }

  // Breadcrumb: split the current path into cumulative ancestors so
  // each is a jumpable link. `/home/beryndil/Projects` →
  //   [ ('/', '/'), ('home', '/home'), ('beryndil', '/home/beryndil'), … ]
  const crumbs = $derived.by(() => {
    if (!currentPath) return [] as Array<{ label: string; path: string }>;
    const segments = currentPath.split('/').filter((s) => s.length > 0);
    const out = [{ label: '/', path: '/' }];
    let acc = '';
    for (const seg of segments) {
      acc += '/' + seg;
      out.push({ label: seg, path: acc });
    }
    return out;
  });
</script>

<div class="flex flex-col gap-1">
  <div class="flex gap-1">
    <input
      type="text"
      class="flex-1 rounded bg-slate-950 border border-slate-800 px-2 py-2 text-sm font-mono
        focus:outline-none focus:border-slate-600"
      {placeholder}
      bind:value
      aria-label="Folder path"
    />
    <button
      type="button"
      class="rounded bg-slate-800 hover:bg-slate-700 px-2 py-2 text-xs text-slate-200"
      onclick={onBrowse}
      aria-expanded={open}
    >
      {open ? 'Close' : 'Browse'}
    </button>
  </div>
  {#if open}
    <div class="rounded border border-slate-800 bg-slate-950 p-2 flex flex-col gap-2">
      <nav
        class="flex flex-wrap items-center gap-0.5 text-xs text-slate-400"
        aria-label="Path breadcrumb"
      >
        {#each crumbs as crumb, i (crumb.path)}
          {#if i > 0}<span class="text-slate-700">/</span>{/if}
          <button
            type="button"
            class="rounded px-1 hover:bg-slate-800 hover:text-slate-200 font-mono"
            onclick={() => fetchList(crumb.path)}
          >
            {crumb.label}
          </button>
        {/each}
      </nav>
      <div class="flex items-center justify-between gap-2 text-xs">
        <button
          type="button"
          class="rounded bg-slate-800 hover:bg-slate-700 px-2 py-1 text-slate-200 disabled:opacity-40"
          onclick={ascend}
          disabled={parent === null}
          aria-label="Go to parent directory"
        >
          ⬆ parent
        </button>
        <label class="inline-flex items-center gap-1 text-slate-400">
          <input
            type="checkbox"
            class="accent-emerald-500"
            checked={showHidden}
            onchange={toggleHidden}
          />
          <span>hidden</span>
        </label>
        <button
          type="button"
          class="rounded bg-emerald-600 hover:bg-emerald-500 px-2 py-1 text-white"
          onclick={useThis}
        >
          Use this folder
        </button>
      </div>
      {#if loading}
        <p class="text-xs text-slate-500">loading…</p>
      {:else if error}
        <p class="text-xs text-rose-400">{error}</p>
      {:else if entries.length === 0}
        <p class="text-xs text-slate-600">(no subdirectories)</p>
      {:else}
        <ul
          class="grid grid-cols-2 gap-1 max-h-48 overflow-y-auto"
          aria-label="Subdirectories"
        >
          {#each entries as entry (entry.path)}
            <li>
              <button
                type="button"
                class="w-full text-left truncate rounded bg-slate-900 hover:bg-slate-800 px-2 py-1 text-xs font-mono text-slate-200"
                onclick={() => descend(entry)}
                title={entry.path}
              >
                {entry.name}
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</div>
