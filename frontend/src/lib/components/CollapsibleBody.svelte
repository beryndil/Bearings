<script lang="ts">
  /**
   * Height-based fold for long message bodies.
   *
   * Measures rendered height with a ResizeObserver. When the inner
   * content exceeds `thresholdPx`, the wrapper clamps to that height,
   * fades the last 64px with a `mask-image`, and shows a "Show full"
   * button beneath the masked content. Once the user expands, the
   * choice is remembered per-message in `localStorage` so reloads and
   * scroll-back don't re-collapse the message underfoot.
   *
   * The default slot receives the rendered markdown body (including
   * `use:highlight`, shiki, prose styles, etc). This component does
   * not care what's inside — it only measures and clamps.
   */
  import { onMount } from 'svelte';
  import { renderMarkdown } from '$lib/render';
  import { highlight } from '$lib/actions/highlight';
  import { contextmenuDelegate } from '$lib/actions/contextmenu-delegate';

  type Props = {
    /** Stable id used for the localStorage persistence key. Null for
     * pre-settled streaming content — collapse is skipped entirely. */
    messageId: string | null;
    content: string;
    highlightQuery: string;
    /** Above this rendered height (px), the body folds by default. */
    thresholdPx?: number;
    /** Disables fold entirely — used for the streaming assistant turn
     * so watchers see new tokens land, not a collapse. */
    disabled?: boolean;
    /** Parent session id — plumbed through so the context-menu
     * delegate can attribute code_block / link right-clicks back to
     * the owning session. Null during the first streaming frames of a
     * brand-new turn. */
    sessionId?: string | null;
  };

  const {
    messageId,
    content,
    highlightQuery,
    thresholdPx = 480,
    disabled = false,
    sessionId = null
  }: Props = $props();

  const STORAGE_PREFIX = 'bearings:msg:expanded:';

  let inner: HTMLDivElement | undefined = $state();
  let contentHeight = $state(0);
  let userExpanded = $state(false);
  let hydrated = $state(false);

  const storageKey = $derived(messageId ? `${STORAGE_PREFIX}${messageId}` : null);
  const overflows = $derived(contentHeight > thresholdPx);
  const shouldFold = $derived(!disabled && overflows && !userExpanded);

  onMount(() => {
    if (storageKey) {
      try {
        userExpanded = localStorage.getItem(storageKey) === '1';
      } catch {
        // localStorage can throw in private mode / blocked contexts —
        // treat as "never expanded before" and move on.
        userExpanded = false;
      }
    }
    hydrated = true;

    if (!inner || typeof ResizeObserver === 'undefined') return;
    const el = inner;
    const ro = new ResizeObserver(() => {
      contentHeight = el.scrollHeight;
    });
    ro.observe(el);
    // Prime the measurement so the first paint doesn't flicker from
    // "not yet measured" → "folded".
    contentHeight = el.scrollHeight;
    return () => ro.disconnect();
  });

  function setExpanded(next: boolean) {
    userExpanded = next;
    if (!storageKey) return;
    try {
      if (next) {
        localStorage.setItem(storageKey, '1');
      } else {
        localStorage.removeItem(storageKey);
      }
    } catch {
      // Persistence is best-effort. If storage is unavailable the
      // in-memory toggle still works for the current page load.
    }
  }
</script>

<div class="collapsible-body" data-testid="collapsible-body">
  <div
    bind:this={inner}
    class="prose prose-invert prose-sm max-w-none collapsible-inner"
    class:is-folded={hydrated && shouldFold}
    style="--collapsed-max: {thresholdPx}px;"
    use:highlight={highlightQuery}
    use:contextmenuDelegate={{ sessionId, messageId }}
    data-testid="collapsible-inner"
    data-folded={hydrated && shouldFold ? 'true' : 'false'}
  >
    {@html renderMarkdown(content)}
  </div>
  {#if hydrated && overflows && !disabled}
    <div class="mt-1 flex justify-center">
      <button
        type="button"
        class="text-[10px] uppercase tracking-wider text-slate-400 hover:text-slate-200
          px-2 py-0.5 rounded border border-slate-700 bg-slate-900/60"
        onclick={() => setExpanded(!userExpanded)}
        data-testid="collapse-toggle"
        aria-expanded={userExpanded}
      >
        {userExpanded ? '⌃ collapse' : '⌄ show full message'}
      </button>
    </div>
  {/if}
</div>

<style>
  .collapsible-inner.is-folded {
    max-height: var(--collapsed-max);
    overflow: hidden;
    -webkit-mask-image: linear-gradient(to top, transparent 0, black 64px);
    mask-image: linear-gradient(to top, transparent 0, black 64px);
  }
</style>
