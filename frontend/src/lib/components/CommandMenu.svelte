<script lang="ts">
  import type { CommandEntry } from '$lib/api';

  type Props = {
    /** All known entries. Parent fetches once per session and passes in. */
    entries: CommandEntry[];
    /** Substring the user has typed after `/`, without the slash. */
    query: string;
    /** True when the menu should be visible. */
    open: boolean;
    /** Fires with the chosen entry's slug (no leading `/`). */
    onSelect: (slug: string) => void;
    /** Fires when the user dismisses the menu (Esc, blur, blank query). */
    onClose: () => void;
  };

  const { entries, query, open, onSelect, onClose }: Props = $props();

  // Rank: prefix > substring-slug > substring-description. Case-insensitive.
  // Ties break on alphabetical slug order (the input is already sorted).
  const filtered = $derived.by(() => {
    const q = query.trim().toLowerCase();
    if (!q) return entries;
    type Scored = { entry: CommandEntry; rank: number };
    const scored: Scored[] = [];
    for (const entry of entries) {
      const slug = entry.slug.toLowerCase();
      const desc = entry.description.toLowerCase();
      let rank: number;
      if (slug.startsWith(q)) rank = 0;
      else if (slug.includes(q)) rank = 1;
      else if (desc.includes(q)) rank = 2;
      else continue;
      scored.push({ entry, rank });
    }
    scored.sort((a, b) => a.rank - b.rank);
    return scored.map((s) => s.entry);
  });

  // Clamp selection as the filtered list shrinks. $derived.by memoises
  // on each tick, so a separate `$effect` guards against out-of-range.
  let selectedIndex = $state(0);

  $effect(() => {
    // Touch filtered.length to re-run when the list changes; open is in
    // scope because the parent passes an updated query which flows here.
    void open;
    void filtered.length;
    if (selectedIndex >= filtered.length) selectedIndex = 0;
  });

  // Public API — the parent delegates arrow-key routing here via refs.
  export function handleKey(e: KeyboardEvent): boolean {
    if (!open || filtered.length === 0) {
      // Even with no matches, Escape should close; everything else falls
      // through to the textarea's default behavior.
      if (open && e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return true;
      }
      return false;
    }
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        selectedIndex = (selectedIndex + 1) % filtered.length;
        return true;
      case 'ArrowUp':
        e.preventDefault();
        selectedIndex =
          (selectedIndex - 1 + filtered.length) % filtered.length;
        return true;
      case 'Enter':
      case 'Tab': {
        e.preventDefault();
        const pick = filtered[selectedIndex];
        if (pick) onSelect(pick.slug);
        return true;
      }
      case 'Escape':
        e.preventDefault();
        onClose();
        return true;
      default:
        return false;
    }
  }

  function scopeLabel(scope: CommandEntry['scope']): string {
    return scope === 'user' ? 'user' : scope;
  }

  function scopeTone(scope: CommandEntry['scope']): string {
    switch (scope) {
      case 'project':
        return 'text-emerald-400';
      case 'plugin':
        return 'text-sky-400';
      default:
        return 'text-slate-500';
    }
  }
</script>

{#if open}
  <div
    class="absolute left-4 right-4 bottom-full mb-2 z-30
      rounded border border-slate-800 bg-slate-900 shadow-lg
      max-h-64 overflow-y-auto"
    role="listbox"
    aria-label="Slash command palette"
  >
    {#if filtered.length === 0}
      <p class="px-3 py-2 text-xs text-slate-500">No matching commands.</p>
    {:else}
      <ul class="flex flex-col">
        {#each filtered as entry, i (entry.slug)}
          <li>
            <button
              type="button"
              role="option"
              aria-selected={i === selectedIndex}
              class="w-full text-left px-3 py-1.5 flex items-baseline gap-2
                hover:bg-slate-800 aria-selected:bg-slate-800"
              onmousedown={(e) => {
                // mousedown (not click) keeps the textarea focused so
                // selection doesn't drop the keyboard cursor.
                e.preventDefault();
                onSelect(entry.slug);
              }}
              onmouseenter={() => (selectedIndex = i)}
            >
              <span class="font-mono text-xs text-slate-200">/{entry.slug}</span>
              <span class="text-[10px] uppercase {scopeTone(entry.scope)}">
                {scopeLabel(entry.scope)}{entry.kind === 'skill' ? '·skill' : ''}
              </span>
              {#if entry.description}
                <span class="text-xs text-slate-500 truncate flex-1 text-right">
                  {entry.description}
                </span>
              {/if}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
{/if}
