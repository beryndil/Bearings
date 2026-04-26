<script lang="ts">
  /**
   * L4.3.2 — Generic preview modal for reply-action sub-agent
   * invocations. Renders whatever `replyActions.view.text` carries,
   * tagged with the action's label. Designed to be agnostic to the
   * action: L4.3.3 ships the `⚔ CRIT` button by adding a prompt
   * template + catalog entry on the backend; this modal needs no
   * change to render its results.
   *
   * Three actions:
   *   - Copy        → puts the rendered text in the clipboard
   *   - Send to     → dispatches `bearings:composer-prefill` so the
   *     composer       parent session's composer pre-fills with the result
   *   - Close        → tears down the stream + modal
   *
   * ESC closes (matching every other modal). Keep the dialog narrow
   * enough to read like a reply summary, not a full-pane wall.
   */

  import { replyActions } from '$lib/stores/replyActions.svelte';
  import { sessions } from '$lib/stores/sessions.svelte';

  const view = $derived(replyActions.state);
  const isOpen = $derived(view.status !== 'idle');

  let copied = $state(false);
  let copyTimer: ReturnType<typeof setTimeout> | null = null;

  function close(): void {
    replyActions.close();
  }

  async function onCopy(): Promise<void> {
    if (!view.text) return;
    try {
      await navigator.clipboard.writeText(view.text);
      copied = true;
      if (copyTimer) clearTimeout(copyTimer);
      copyTimer = setTimeout(() => {
        copied = false;
      }, 1500);
    } catch {
      // Clipboard denied (typically a non-https origin without
      // user-gesture). Silent — the user sees no `✓ copied` and
      // can fall back to selecting + ctrl+c on the visible text.
    }
  }

  function onSendToComposer(): void {
    const targetSession = view.sessionId ?? sessions.selectedId;
    if (!targetSession || !view.text) {
      close();
      return;
    }
    window.dispatchEvent(
      new CustomEvent('bearings:composer-prefill', {
        detail: { sessionId: targetSession, text: view.text }
      })
    );
    close();
  }

  // ESC closes the modal. Captured at window level so a focus on a
  // textarea inside the conversation doesn't steal the key.
  $effect(() => {
    if (!isOpen) return;
    function onKey(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        close();
      }
    }
    window.addEventListener('keydown', onKey, { capture: true });
    return () => window.removeEventListener('keydown', onKey, { capture: true });
  });

  // Format cost as a small "$0.0123" string. Null cost (synthetic
  // completion / older SDK) renders as a dash.
  const costLabel = $derived.by(() => {
    if (view.costUsd === null || view.costUsd === undefined) return '—';
    return `$${view.costUsd.toFixed(4)}`;
  });
</script>

{#if isOpen}
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80
      backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
    aria-labelledby="reply-action-title"
    data-testid="reply-action-modal"
  >
    <div
      class="bg-slate-900 border border-sky-800 rounded-lg shadow-2xl w-full
        max-w-2xl mx-4 flex flex-col max-h-[80vh]"
    >
      <header class="px-5 py-3 border-b border-slate-800 flex items-center
        justify-between gap-3">
        <h2
          id="reply-action-title"
          class="text-sm font-medium text-sky-200 flex items-center gap-2"
        >
          <span
            class="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded
              bg-sky-900 text-sky-200"
            data-testid="reply-action-label"
          >
            {view.label || view.action}
          </span>
          <span class="text-slate-400 text-xs">Sub-agent preview</span>
        </h2>
        <span class="text-[10px] uppercase tracking-wider text-slate-500">
          {#if view.status === 'streaming'}
            streaming…
          {:else if view.status === 'complete'}
            done · {costLabel}
          {:else if view.status === 'cancelled'}
            cancelled
          {:else if view.status === 'error'}
            error
          {/if}
        </span>
      </header>

      <div
        class="flex-1 overflow-y-auto px-5 py-4 text-sm text-slate-200
          whitespace-pre-wrap break-words font-mono"
        data-testid="reply-action-body"
      >
        {#if view.status === 'error'}
          <p class="text-rose-300">{view.errorMessage}</p>
        {:else if view.text}
          {view.text}{#if view.status === 'streaming'}<span
              class="inline-block animate-pulse">▍</span
            >{/if}
        {:else if view.status === 'streaming'}
          <p class="text-slate-500 italic">Spawning sub-agent…</p>
        {:else}
          <p class="text-slate-500 italic">No content.</p>
        {/if}
      </div>

      <footer
        class="px-5 py-3 border-t border-slate-800 flex justify-end gap-2"
      >
        <button
          type="button"
          class="px-3 py-1.5 text-xs rounded bg-slate-800 text-slate-200
            hover:bg-slate-700 disabled:opacity-50"
          onclick={onCopy}
          disabled={!view.text}
          data-testid="reply-action-copy"
        >
          {copied ? '✓ copied' : '⎘ copy'}
        </button>
        <button
          type="button"
          class="px-3 py-1.5 text-xs rounded bg-slate-800 text-slate-200
            hover:bg-slate-700 disabled:opacity-50"
          onclick={onSendToComposer}
          disabled={!view.text || view.status === 'streaming'}
          data-testid="reply-action-send"
          title={view.status === 'streaming'
            ? 'Wait for the stream to finish'
            : 'Pre-fill composer with this preview'}
        >
          send to composer
        </button>
        <button
          type="button"
          class="px-3 py-1.5 text-xs rounded bg-emerald-600 text-white
            hover:bg-emerald-500"
          onclick={close}
          data-testid="reply-action-close"
        >
          {view.status === 'streaming' ? 'Cancel' : 'Close'}
        </button>
      </footer>
    </div>
  </div>
{/if}
