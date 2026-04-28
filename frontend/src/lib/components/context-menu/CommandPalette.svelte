<script lang="ts">
  import { tick } from 'svelte';
  import { contextMenu } from '$lib/context-menu/store.svelte';
  import { palette } from '$lib/context-menu/palette.svelte';
  import {
    collectPaletteEntries,
    filterEntries,
    type PaletteEntry,
    type TargetResolver,
  } from '$lib/context-menu/palette-resolver';
  import { sessions } from '$lib/stores/sessions.svelte';
  import type { ActionContext, TargetType } from '$lib/context-menu/types';

  /**
   * Ctrl+Shift+P command palette — Phase 4b.
   *
   * Enumerates every action in the registry whose target can be
   * auto-resolved from current app state. Today that's session-scoped
   * actions tied to `sessions.selected`; other target types (tag /
   * tag_chip / message) are reachable via right-click and intentionally
   * *not* surfaced in the palette — see the header comment in
   * `palette-resolver.ts` for the rationale.
   *
   * Owned invariants:
   *   - Only one palette visible; Ctrl+Shift+P toggles the store.
   *   - Opening the palette closes the context menu (they share the
   *     z-50 layer and the Esc-to-dismiss contract).
   *   - Query resets on every open — palette entries live on stores
   *     that can change underneath, so a stale filter reapplied to a
   *     new-contents list is worse than making the user retype.
   */

  // Target-types we auto-resolve. Add more as target resolvers appear.
  const PALETTE_TYPES: readonly TargetType[] = ['session'];

  /** Resolve a target from current app state. Returns `null` when
   * there's no sensible default — the resolver drops the whole type
   * in that case. */
  const resolver: TargetResolver = (type) => {
    if (type === 'session') {
      const id = sessions.selectedId;
      return id ? { type: 'session', id } : null;
    }
    return null;
  };

  // Rebuild entries whenever the palette opens. Stores referenced by
  // `requires` / `disabled` are Svelte-reactive state, so a re-derive
  // fires on every change — but we only care while `open`.
  const entries = $derived.by<PaletteEntry[]>(() => {
    if (!palette.open) return [];
    return collectPaletteEntries(resolver, PALETTE_TYPES);
  });

  const filtered = $derived<PaletteEntry[]>(
    palette.open ? filterEntries(entries, palette.query) : []
  );

  let selectedIndex = $state(0);
  let queryEl: HTMLInputElement | undefined = $state();

  // Close the context menu when the palette opens, and focus the query
  // on open. Also reset the selected index when the filter result set
  // changes so the highlight doesn't sit off the end.
  $effect(() => {
    if (palette.open) {
      contextMenu.close();
      // Defer focus until after the DOM renders the input.
      tick().then(() => queryEl?.focus());
    }
  });

  $effect(() => {
    // Re-run on every filtered-length change; clamp to [0, len).
    const len = filtered.length;
    if (selectedIndex >= len) selectedIndex = 0;
    if (selectedIndex < 0) selectedIndex = 0;
  });

  function onBackdropMousedown(e: MouseEvent): void {
    // Only the backdrop closes — clicks inside the dialog bubble here
    // too because it sits inside this onmousedown handler's element.
    const target = e.target as HTMLElement | null;
    if (!target) return;
    if (target.dataset.backdrop === '1') {
      palette.hide();
    }
  }

  async function activate(idx: number): Promise<void> {
    const entry = filtered[idx];
    if (!entry) return;
    if (entry.disabledReason) return;
    const ctx: ActionContext = {
      target: entry.target,
      event: null,
      advanced: false,
    };
    // Close first so a handler that opens another modal (ConfirmDialog)
    // doesn't layer on top of the palette — ConfirmDialog owns the
    // confirm-flow UI and the palette is just a launcher.
    palette.hide();
    try {
      await entry.action.handler(ctx);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('[palette] handler threw', entry.id, err);
    }
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      e.preventDefault();
      palette.hide();
      return;
    }
    if (filtered.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      selectedIndex = (selectedIndex + 1) % filtered.length;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      selectedIndex = (selectedIndex - 1 + filtered.length) % filtered.length;
    } else if (e.key === 'Home') {
      e.preventDefault();
      selectedIndex = 0;
    } else if (e.key === 'End') {
      e.preventDefault();
      selectedIndex = filtered.length - 1;
    } else if (e.key === 'Enter') {
      e.preventDefault();
      void activate(selectedIndex);
    }
  }
</script>

{#if palette.open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/80 px-4 pt-24"
    data-backdrop="1"
    onmousedown={onBackdropMousedown}
    data-testid="command-palette-backdrop"
  >
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      tabindex="-1"
      class="flex w-full max-w-xl flex-col overflow-hidden rounded-lg border
        border-slate-800 bg-slate-900 shadow-2xl"
      data-testid="command-palette"
      onkeydown={onKey}
    >
      <div class="border-b border-slate-800 p-3">
        <input
          type="text"
          bind:this={queryEl}
          bind:value={palette.query}
          class="w-full rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm
            focus:border-slate-600 focus:outline-none"
          placeholder="Run an action… (type to filter, ↑/↓ to navigate, Enter to run)"
          aria-label="Palette query"
          data-testid="command-palette-query"
        />
      </div>

      <ul
        class="max-h-80 overflow-y-auto"
        role="listbox"
        aria-label="Palette results"
        data-testid="command-palette-list"
      >
        {#if filtered.length === 0}
          <li class="px-3 py-4 text-xs text-slate-500">
            {#if entries.length === 0}
              Open a session first — the palette lists actions for the currently-selected session.
            {:else}
              No matching actions.
            {/if}
          </li>
        {:else}
          {#each filtered as entry, i (entry.id)}
            {@const hi = i === selectedIndex}
            {@const disabled = entry.disabledReason !== null}
            <li>
              <button
                type="button"
                role="option"
                aria-selected={hi}
                {disabled}
                class="flex w-full items-baseline gap-3 border-b border-slate-800/60
                  px-3 py-2 text-left last:border-b-0
                  hover:bg-slate-800 disabled:cursor-not-allowed
                  disabled:opacity-50 aria-selected:bg-slate-800"
                title={entry.disabledReason ?? undefined}
                onmousedown={(e) => {
                  // mousedown (not click) so the query input doesn't
                  // lose focus → regain focus → submit cycle.
                  e.preventDefault();
                  void activate(i);
                }}
                onmouseenter={() => (selectedIndex = i)}
                data-testid="command-palette-row"
                data-action-id={entry.id}
                data-disabled={disabled ? '1' : '0'}
              >
                <span class="flex-1 truncate text-sm text-slate-200">
                  {entry.label}
                  {#if entry.advanced}
                    <span class="ml-1 text-[9px] uppercase tracking-wider text-amber-400">
                      adv
                    </span>
                  {/if}
                </span>
                <span class="text-[10px] uppercase text-slate-500">
                  {entry.section}
                </span>
                <span class="shrink-0 font-mono text-[10px] text-slate-600">
                  {entry.id}
                </span>
              </button>
            </li>
          {/each}
        {/if}
      </ul>

      <footer
        class="flex items-center justify-between border-t border-slate-800 px-3
          py-1.5 text-[10px] text-slate-500"
      >
        <span>
          {filtered.length} / {entries.length} action{entries.length === 1 ? '' : 's'}
        </span>
        <span>
          <kbd class="rounded border border-slate-800 bg-slate-950 px-1 py-0.5 font-mono">
            Esc
          </kbd>
          to close
        </span>
      </footer>
    </div>
  </div>
{/if}
