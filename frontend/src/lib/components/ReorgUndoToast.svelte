<script lang="ts">
  import { onDestroy } from 'svelte';

  import type { ReorgWarning } from '$lib/api';

  // Slice 3 of the Session Reorg plan
  // (`~/.claude/plans/sparkling-triaging-otter.md`). A transient
  // bottom-right toast that gives the user a 30-second window to
  // reverse the last reorg op. The parent provides:
  //   - `onUndo` — a closure that runs the inverse move and resolves
  //     when complete. The toast disables the button while awaiting.
  //   - `onDismiss` — fired on either timeout elapsed, explicit × tap,
  //     or a successful undo. Clears the parent's pending-op state.
  //
  // Slice 7 added optional `warnings` — advisory flags from the
  // server (currently only "orphan_tool_call" for split/move ops that
  // would separate a tool call from its result). Rendered as a
  // collapsed amber block above the main message so the user can
  // decide whether to Undo before the window elapses. Never fatal —
  // the op has already committed by the time the toast mounts.

  type Props = {
    message: string;
    /** Advisory warnings from the server. Omit or pass `[]` when the
     * caller has nothing to surface — the warn block hides entirely
     * in that case so the toast stays compact on the common path. */
    warnings?: ReorgWarning[];
    /** Milliseconds of grace period. Defaults to 30_000 per plan. */
    windowMs?: number;
    onUndo: () => Promise<void> | void;
    onDismiss: () => void;
  };

  const { message, warnings = [], windowMs = 30_000, onUndo, onDismiss }: Props = $props();

  const startedAt = Date.now();
  let remaining = $state(30);
  let undoing = $state(false);
  let done = $state(false);

  // Countdown tick + auto-dismiss. Kept as a setInterval rather than
  // one timeout per second because we show a live counter; the grid
  // is stable and we only read `Date.now()` once to avoid drift.
  const tick = setInterval(() => {
    // Reading `windowMs` inside the closure is the pattern Svelte 5
    // recommends — it stays reactive to prop changes. In practice a
    // toast instance is short-lived and its props are stable; the
    // parent replaces-not-mutates when a new reorg op starts.
    const elapsed = Date.now() - startedAt;
    const left = Math.max(0, Math.ceil((windowMs - elapsed) / 1000));
    remaining = left;
    if (left === 0 && !done) {
      done = true;
      clearInterval(tick);
      onDismiss();
    }
  }, 250);

  onDestroy(() => clearInterval(tick));

  async function runUndo() {
    if (undoing || done) return;
    undoing = true;
    try {
      await onUndo();
      done = true;
      clearInterval(tick);
      onDismiss();
    } finally {
      undoing = false;
    }
  }

  function dismiss() {
    if (done) return;
    done = true;
    clearInterval(tick);
    onDismiss();
  }
</script>

{#if !done}
  <div
    class="fixed bottom-4 right-4 z-50 flex max-w-sm flex-col gap-2
      rounded-lg border border-slate-700 bg-slate-900 px-4 py-3 shadow-2xl"
    role="status"
    aria-live="polite"
    data-testid="reorg-undo-toast"
  >
    {#if warnings.length > 0}
      <ul
        class="space-y-0.5 rounded border border-amber-500/40 bg-amber-500/10
          px-2 py-1 text-[11px] text-amber-300"
        data-testid="reorg-undo-warnings"
      >
        {#each warnings as warning (warning.code + warning.message)}
          <li data-testid="reorg-undo-warning" data-warning-code={warning.code}>
            <span class="mr-1" aria-hidden="true">⚠</span>{warning.message}
          </li>
        {/each}
      </ul>
    {/if}
    <div class="flex items-center gap-3">
      <span class="flex-1 text-xs text-slate-200">
        {message}
      </span>
      <button
        type="button"
        class="text-xs font-medium text-amber-300 hover:text-amber-200 disabled:opacity-50"
        onclick={runUndo}
        disabled={undoing}
        data-testid="reorg-undo-button"
      >
        {undoing ? 'Undoing…' : `Undo (${remaining}s)`}
      </button>
      <button
        type="button"
        class="text-xs text-slate-500 hover:text-slate-300"
        aria-label="Dismiss undo toast"
        onclick={dismiss}
      >
        ✕
      </button>
    </div>
  </div>
{/if}
