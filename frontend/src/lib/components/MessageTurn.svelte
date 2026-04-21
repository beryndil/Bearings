<script lang="ts">
  import type { Message } from '$lib/api';
  import type { LiveToolCall } from '$lib/stores/conversation.svelte';
  import { renderMarkdown } from '$lib/render';
  import { highlight } from '$lib/actions/highlight';
  import { stickToBottom } from '$lib/actions/autoscroll';

  type Props = {
    user: Message | null;
    assistant: Message | null;
    thinking: string;
    toolCalls: LiveToolCall[];
    streamingContent: string;
    streamingThinking: string;
    isStreaming: boolean;
    highlightQuery: string;
    copiedMsgId: string | null;
    onCopyMessage: (msg: Message) => void;
  };

  const {
    user,
    assistant,
    thinking,
    toolCalls,
    streamingContent,
    streamingThinking,
    isStreaming,
    highlightQuery,
    copiedMsgId,
    onCopyMessage
  }: Props = $props();

  function statusBadge(ok: boolean | null): { label: string; classes: string } {
    if (ok === null) return { label: 'running', classes: 'bg-amber-900 text-amber-300' };
    if (ok) return { label: 'ok', classes: 'bg-emerald-900 text-emerald-300' };
    return { label: 'error', classes: 'bg-rose-900 text-rose-300' };
  }

  const runningCount = $derived(toolCalls.filter((t) => t.ok === null).length);
  const thinkingCombined = $derived(thinking + streamingThinking);
</script>

{#if user}
  <article class="rounded border border-slate-800 bg-slate-800/60 px-3 py-2">
    <header class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">user</header>
    <div class="prose prose-invert prose-sm max-w-none" use:highlight={highlightQuery}>
      {@html renderMarkdown(user.content)}
    </div>
  </article>
{/if}

{#if thinkingCombined}
  <details class="ml-6 rounded bg-slate-950/40 border border-slate-800/60 px-2 py-1">
    <summary class="cursor-pointer text-[10px] uppercase tracking-wider text-slate-500">
      thinking{isStreaming ? ' · live' : ''}
    </summary>
    <pre
      class="mt-1 whitespace-pre-wrap text-xs text-slate-400 font-sans">{thinkingCombined}</pre>
  </details>
{/if}

{#if toolCalls.length > 0}
  <details class="ml-6 rounded bg-slate-950/40 border border-slate-800/60 px-2 py-1">
    <summary
      class="cursor-pointer text-[10px] uppercase tracking-wider text-slate-500
        flex items-center gap-2"
    >
      <span>tool work · {toolCalls.length}</span>
      {#if runningCount > 0}
        <span class="bg-amber-900 text-amber-300 px-1.5 py-0.5 rounded text-[9px] uppercase">
          {runningCount} running
        </span>
      {/if}
    </summary>
    <ul class="flex flex-col gap-1.5 mt-2">
      {#each toolCalls as call (call.id)}
        {@const badge = statusBadge(call.ok)}
        {@const streamLen =
          (call.output?.length ?? 0) + (call.error?.length ?? 0)}
        <li
          class="tool-card rounded border border-slate-800 bg-slate-950/40
            text-xs overflow-hidden"
        >
          <details>
            <summary
              class="cursor-pointer p-1.5 flex items-center justify-between
                gap-2 hover:bg-slate-900/40"
            >
              <span class="font-mono font-medium truncate">{call.name}</span>
              <span
                class="{badge.classes} px-1.5 py-0.5 rounded text-[10px] uppercase"
              >
                {badge.label}
              </span>
            </summary>
            <div
              use:stickToBottom={streamLen}
              class="max-h-64 overflow-y-auto bg-black/70 border-t border-slate-800
                p-2 font-mono text-[10px] leading-relaxed"
            >
              <pre
                class="whitespace-pre-wrap break-all text-slate-300"><span
                  class="text-emerald-400">$ {call.name}</span>
{JSON.stringify(call.input, null, 2)}{#if call.output !== null}

{call.output}{/if}{#if call.error}

<span class="text-rose-400">error: {call.error}</span>{/if}</pre>
            </div>
          </details>
        </li>
      {/each}
    </ul>
  </details>
{/if}

{#if assistant || isStreaming}
  <article
    class="rounded border px-3 py-2 bg-slate-900
      {isStreaming ? 'border-amber-900/50' : 'border-slate-800'}"
  >
    <header
      class="text-[10px] uppercase tracking-wider mb-1
        {isStreaming ? 'text-amber-400' : 'text-slate-500'}"
    >
      assistant{isStreaming ? ' · streaming' : ''}
    </header>
    <div class="prose prose-invert prose-sm max-w-none" use:highlight={highlightQuery}>
      {#if assistant}
        {@html renderMarkdown(assistant.content)}
      {:else}
        {@html renderMarkdown(streamingContent)}
        <span class="inline-block animate-pulse">▍</span>
      {/if}
    </div>
    {#if assistant}
      <div class="mt-2 flex justify-end">
        <button
          type="button"
          class="text-[10px] uppercase tracking-wider text-slate-500 hover:text-slate-300"
          aria-label="Copy reply to clipboard"
          title={copiedMsgId === assistant.id ? 'Copied' : 'Copy reply'}
          onclick={() => onCopyMessage(assistant)}
        >
          {copiedMsgId === assistant.id ? '✓ copied' : '⎘ copy'}
        </button>
      </div>
    {/if}
  </article>
{/if}

<style>
  /* Keep the tool-call card header looking like the old always-visible
   * row — no default disclosure triangle. The whole summary is the
   * click target; hover tint makes expandability discoverable. */
  .tool-card > details > summary {
    list-style: none;
  }
  .tool-card > details > summary::-webkit-details-marker {
    display: none;
  }
</style>
