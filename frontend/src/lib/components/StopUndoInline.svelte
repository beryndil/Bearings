<script lang="ts">
  import { onDestroy } from 'svelte';

  import { agent } from '$lib/agent.svelte';

  // Inline replacement for the Stop button during the STOP_DELAY_MS
  // grace window added for the session-switch-interrupt investigation
  // (TODO.md "TEMP probe — session-switch interrupt diagnostic").
  //
  // Renders the countdown + Undo where the Stop button used to sit —
  // Conversation header, ChecklistChat header — so the feedback lands
  // where the user's cursor was rather than bottom-right of the page.
  // Hidden unless a stop is actually pending; callers render it as a
  // sibling of their Stop button and let the `{#if}` guard handle
  // visibility.

  const startedAt = $derived(agent.stopPendingStartedAt);
  const windowMs = agent.stopPendingWindowMs;

  // A ticking `now` so the countdown updates live. 250ms is the same
  // cadence the UndoToast uses, fine-grained enough for the 3-second
  // window without being wasteful.
  let now = $state(Date.now());
  const tick = setInterval(() => (now = Date.now()), 250);
  onDestroy(() => clearInterval(tick));

  const remainingSec = $derived(
    startedAt === null ? 0 : Math.max(0, Math.ceil((windowMs - (now - startedAt)) / 1000))
  );
</script>

{#if startedAt !== null}
  <span
    class="inline-flex items-center gap-2 rounded border border-amber-700
      bg-amber-900/70 px-2 py-1 text-[10px] uppercase tracking-wider text-amber-100"
    role="status"
    aria-live="polite"
    data-testid="stop-undo-inline"
  >
    <span>Stopping {remainingSec}s</span>
    <button
      type="button"
      class="font-medium text-amber-200 hover:text-white"
      onclick={() => agent.cancelPendingStop()}
      data-testid="stop-undo-button"
    >
      Undo
    </button>
  </span>
{/if}
