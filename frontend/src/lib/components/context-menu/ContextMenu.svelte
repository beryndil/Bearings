<script lang="ts">
  import { contextMenu } from '$lib/context-menu/store.svelte';
  import { placeAtCursor } from '$lib/context-menu/positioning';
  import { resolveMenu } from '$lib/context-menu/registry';
  import type { ActionContext } from '$lib/context-menu/types';
  import ContextMenuItem from './ContextMenuItem.svelte';

  // Default menu size used before the real <nav> is measured. Picked
  // to match the Phase 1 action labels; Phase 2's flip math will
  // measure post-mount and re-place.
  const DEFAULT_WIDTH_PX = 220;
  const DEFAULT_HEIGHT_PX = 48;

  let menuEl: HTMLElement | undefined = $state();

  // Resolve the menu spec only while open. Calling resolveMenu on a
  // null target is pointless and would force defensive branches below.
  const rendered = $derived.by(() => {
    const s = contextMenu.state;
    if (!s.open || s.target === null) return null;
    return resolveMenu(s.target, s.advanced);
  });

  const placement = $derived.by(() => {
    const s = contextMenu.state;
    if (!s.open) return { left: 0, top: 0 };
    return placeAtCursor({
      x: s.x,
      y: s.y,
      menuWidth: menuEl?.offsetWidth ?? DEFAULT_WIDTH_PX,
      menuHeight: menuEl?.offsetHeight ?? DEFAULT_HEIGHT_PX,
      viewportWidth: typeof window === 'undefined' ? 0 : window.innerWidth,
      viewportHeight: typeof window === 'undefined' ? 0 : window.innerHeight
    });
  });

  // While open, Escape closes and any click outside the menu closes.
  // A second right-click on a target re-opens at new coords via the
  // store; re-opening while already open just moves the menu.
  $effect(() => {
    if (!contextMenu.state.open) return;
    function onKey(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        e.preventDefault();
        contextMenu.close();
      }
    }
    function onClick(e: MouseEvent): void {
      const target = e.target as Node | null;
      if (target && menuEl && menuEl.contains(target)) return;
      contextMenu.close();
    }
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onClick);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onClick);
    };
  });

  function ctxFor(): ActionContext {
    const s = contextMenu.state;
    // `target` is guaranteed non-null by the `#if rendered` guard in
    // the template; still narrow defensively for the compiler.
    return {
      target: s.target!,
      event: null,
      advanced: s.advanced
    };
  }

  function onDone(): void {
    contextMenu.close();
  }

  // Suppress the browser's native menu on the menu itself — §spec
  // "No context menu on the menu itself."
  function onOwnContextMenu(e: MouseEvent): void {
    e.preventDefault();
  }
</script>

{#if rendered}
  <div
    bind:this={menuEl}
    role="menu"
    aria-label="Context menu"
    tabindex="-1"
    data-testid="context-menu"
    data-target-type={rendered.target.type}
    data-advanced={rendered.advanced}
    class="fixed z-50 min-w-[12rem] max-w-xs rounded border border-slate-700
      bg-slate-900 shadow-xl py-1 text-slate-200"
    style="left: {placement.left}px; top: {placement.top}px;"
    oncontextmenu={onOwnContextMenu}
  >
    {#each rendered.groups as group, i (group.section)}
      {#if i > 0}
        <div class="my-1 h-px bg-slate-800" role="separator"></div>
      {/if}
      {#each group.actions as action (action.id)}
        <ContextMenuItem {action} ctx={ctxFor()} {onDone} />
      {/each}
    {/each}
  </div>
{/if}
