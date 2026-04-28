<script lang="ts">
  import type { ApprovalRequestEvent } from '$lib/api';

  type Props = {
    request: ApprovalRequestEvent;
    connected: boolean;
    onRespond: (requestId: string, decision: 'allow' | 'deny', reason?: string) => boolean;
  };

  const { request, connected, onRespond }: Props = $props();

  // Pretty-printed tool input. JSON.stringify handles nested objects /
  // arrays; toolInputText is used for the preformatted display block.
  const toolInputText = $derived(
    Object.keys(request.input).length === 0 ? '(no input)' : JSON.stringify(request.input, null, 2)
  );

  // Set to the attempted decision while the response is in-flight so
  // the button text flips to "sending…" and a failed send (socket down)
  // rolls back to the idle state. Single source of truth prevents a
  // double-click from firing two responses.
  let pending = $state<'allow' | 'deny' | null>(null);

  function respond(decision: 'allow' | 'deny'): void {
    if (pending !== null) return;
    pending = decision;
    const ok = onRespond(request.request_id, decision);
    if (!ok) {
      // Socket not open — leave the modal visible, let the user retry
      // after reconnect. The backend Future is still parked.
      pending = null;
    }
  }

  // ESC must NOT resolve the gate. Swallow it at the window level so
  // other components (search highlight, textarea focus) don't act on
  // it while the modal is up. Approval is click-only.
  $effect(() => {
    function onKey(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
      }
    }
    window.addEventListener('keydown', onKey, { capture: true });
    return () => window.removeEventListener('keydown', onKey, { capture: true });
  });
</script>

<div
  class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80
    backdrop-blur-sm"
  role="dialog"
  aria-modal="true"
  aria-labelledby="approval-title"
  data-testid="approval-modal"
>
  <div
    class="mx-4 w-full max-w-lg rounded-lg border border-sky-800
      bg-slate-900 shadow-2xl"
  >
    <header class="border-b border-slate-800 px-5 py-3">
      <h2 id="approval-title" class="flex items-center gap-2 text-sm font-medium text-sky-200">
        <span
          class="rounded bg-sky-900 px-1.5 py-0.5 text-[10px] uppercase
            tracking-wider text-sky-200"
        >
          approval
        </span>
        Tool permission request
      </h2>
    </header>

    <div class="flex flex-col gap-3 px-5 py-4">
      <p class="text-sm text-slate-300">
        The agent wants to use
        <span class="font-mono text-sky-300">{request.tool_name}</span>.
      </p>
      <div>
        <p class="mb-1 text-[10px] uppercase tracking-wider text-slate-500">Input</p>
        <pre
          class="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded border border-slate-800
            bg-slate-950 px-3 py-2 font-mono
            text-xs text-slate-300"
          data-testid="approval-input">{toolInputText}</pre>
      </div>
      {#if !connected}
        <p class="text-xs text-amber-300">
          Reconnecting — your response will send once the socket is back.
        </p>
      {/if}
    </div>

    <footer class="flex justify-end gap-2 border-t border-slate-800 px-5 py-3">
      <button
        type="button"
        class="rounded bg-slate-800 px-3 py-1.5 text-xs text-slate-200
          hover:bg-slate-700 disabled:opacity-50"
        onclick={() => respond('deny')}
        disabled={pending !== null || !connected}
        data-testid="approval-deny"
      >
        {pending === 'deny' ? 'Denying…' : 'Deny'}
      </button>
      <button
        type="button"
        class="rounded bg-emerald-600 px-3 py-1.5 text-xs text-white
          hover:bg-emerald-500 disabled:opacity-50"
        onclick={() => respond('allow')}
        disabled={pending !== null || !connected}
        data-testid="approval-allow"
      >
        {pending === 'allow' ? 'Approving…' : 'Approve'}
      </button>
    </footer>
  </div>
</div>
