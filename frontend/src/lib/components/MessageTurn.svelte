<script lang="ts">
  import type { Message } from '$lib/api';
  import type { LiveToolCall } from '$lib/stores/conversation.svelte';
  import { stickToBottom } from '$lib/actions/autoscroll';
  import { contextmenu } from '$lib/actions/contextmenu';
  import CollapsibleBody from './CollapsibleBody.svelte';

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
    /** Slice 3: per-message reorg menu. Optional so tests / older
     * callers that don't care about reorg can omit them. */
    onMoveMessage?: (msg: Message) => void;
    onSplitAfter?: (msg: Message) => void;
    /** Slice 4: bulk-select mode. When `bulkMode` is true, the `⋯`
     * menu is hidden and a checkbox renders in the message header
     * instead. `selectedIds` is the live set; toggling a row fires
     * `onToggleSelect` with the message and whether Shift was held
     * (for range selection, handled by the parent). */
    bulkMode?: boolean;
    selectedIds?: ReadonlySet<string>;
    onToggleSelect?: (msg: Message, shiftKey: boolean) => void;
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
    onCopyMessage,
    onMoveMessage,
    onSplitAfter,
    bulkMode = false,
    selectedIds,
    onToggleSelect
  }: Props = $props();

  const runningCount = $derived(toolCalls.filter((t) => t.ok === null).length);
  const thinkingCombined = $derived(thinking + streamingThinking);

  // Aggregate signal for the stick-to-bottom action: grows whenever a
  // new call appears or any existing call's output/error lengthens.
  const toolStreamSignal = $derived(
    toolCalls.reduce(
      (acc, c) => acc + (c.output?.length ?? 0) + (c.error?.length ?? 0),
      toolCalls.length
    )
  );

  function callMarker(ok: boolean | null): { glyph: string; cls: string } {
    if (ok === null) return { glyph: '●', cls: 'text-amber-400' };
    if (ok) return { glyph: '✓', cls: 'text-emerald-400' };
    return { glyph: '✗', cls: 'text-rose-400' };
  }

  // Slice 3: per-message menu. Track which message id currently has
  // its popover open — only one at a time. A document-level click
  // handler dismisses it on outside taps.
  let openMenuId = $state<string | null>(null);

  const reorgEnabled = $derived(Boolean(onMoveMessage || onSplitAfter));

  $effect(() => {
    if (openMenuId === null) return;
    function onDocClick(e: MouseEvent) {
      const tgt = e.target as HTMLElement | null;
      if (tgt && tgt.closest('[data-reorg-menu]')) return;
      openMenuId = null;
    }
    document.addEventListener('click', onDocClick);
    return () => document.removeEventListener('click', onDocClick);
  });

  function toggleMenu(id: string) {
    openMenuId = openMenuId === id ? null : id;
  }

  function handleMove(msg: Message) {
    openMenuId = null;
    onMoveMessage?.(msg);
  }

  function handleSplit(msg: Message) {
    openMenuId = null;
    onSplitAfter?.(msg);
  }

  function isSelected(id: string): boolean {
    return selectedIds?.has(id) ?? false;
  }

  function onCheckboxClick(e: MouseEvent, msg: Message) {
    // The checkbox itself is triggered by the browser before this
    // handler fires; we intercept to deliver the shiftKey flag to
    // the parent so shift-click-range logic lives in one place.
    e.preventDefault();
    onToggleSelect?.(msg, e.shiftKey);
  }
</script>

{#if user}
  <article
    class="relative rounded border px-3 py-2 group
      {bulkMode && isSelected(user.id)
        ? 'border-emerald-500 bg-emerald-900/10'
        : 'border-slate-800 bg-slate-800/60'}"
    data-testid="user-article"
    data-message-id={user.id}
    use:contextmenu={{
      target: {
        type: 'message',
        id: user.id,
        sessionId: user.session_id,
        role: 'user'
      }
    }}
  >
    <header
      class="flex items-center justify-between text-[10px] uppercase tracking-wider
        text-slate-500 mb-1"
    >
      <span class="flex items-center gap-2">
        {#if bulkMode}
          <input
            type="checkbox"
            class="accent-emerald-500 cursor-pointer"
            aria-label={`Select user message ${user.id}`}
            checked={isSelected(user.id)}
            onclick={(e) => onCheckboxClick(e, user!)}
            data-testid="bulk-checkbox"
            data-message-id={user.id}
          />
        {/if}
        <span>user</span>
      </span>
      {#if reorgEnabled && !bulkMode}
        <div class="relative" data-reorg-menu>
          <button
            type="button"
            class="opacity-0 group-hover:opacity-100 focus:opacity-100 text-slate-400
              hover:text-slate-200 px-1"
            aria-label="Message actions"
            aria-haspopup="menu"
            aria-expanded={openMenuId === user.id}
            onclick={(e) => {
              e.stopPropagation();
              toggleMenu(user!.id);
            }}
            data-testid="message-menu-trigger"
            data-message-id={user.id}
          >
            ⋯
          </button>
          {#if openMenuId === user.id}
            <div
              class="absolute right-0 top-full mt-1 z-10 rounded border border-slate-700
                bg-slate-900 shadow-lg py-1 min-w-[10rem]"
              role="menu"
              data-testid="message-menu"
            >
              {#if onMoveMessage}
                <button
                  type="button"
                  class="block w-full text-left px-3 py-1 text-xs text-slate-200
                    hover:bg-slate-800"
                  role="menuitem"
                  onclick={() => handleMove(user!)}
                  data-testid="menu-move"
                >
                  Move to session…
                </button>
              {/if}
              {#if onSplitAfter}
                <button
                  type="button"
                  class="block w-full text-left px-3 py-1 text-xs text-slate-200
                    hover:bg-slate-800"
                  role="menuitem"
                  onclick={() => handleSplit(user!)}
                  data-testid="menu-split"
                >
                  Split here…
                </button>
              {/if}
            </div>
          {/if}
        </div>
      {/if}
    </header>
    <CollapsibleBody
      messageId={user.id}
      content={user.content}
      highlightQuery={highlightQuery}
    />
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
    <div
      use:stickToBottom={toolStreamSignal}
      class="mt-2 max-h-80 overflow-y-auto rounded border border-slate-800
        bg-black/70 p-2 font-mono text-[10px] leading-relaxed text-slate-300"
    >
      {#each toolCalls as call, i (call.id)}
        {@const mark = callMarker(call.ok)}
        <pre
          class="whitespace-pre-wrap break-all {i > 0 ? 'mt-3' : ''}"><span
            class="text-emerald-400">$ {call.name}</span> <span
            class={mark.cls}>{mark.glyph}</span>{#if call.outputTruncated} <span
            class="text-amber-400">[truncated]</span>{/if}
{JSON.stringify(call.input, null, 2)}{#if call.output !== null}
{call.output}{/if}{#if call.error}
<span class="text-rose-400">error: {call.error}</span>{/if}</pre>
      {/each}
    </div>
  </details>
{/if}

{#if assistant || isStreaming}
  <article
    class="relative rounded border px-3 py-2 bg-slate-900 group
      {bulkMode && assistant && isSelected(assistant.id)
        ? 'border-emerald-500 bg-emerald-900/10'
        : isStreaming
          ? 'border-amber-900/50'
          : 'border-slate-800'}"
    data-testid="assistant-article"
    data-message-id={assistant?.id ?? ''}
    use:contextmenu={{
      target: assistant
        ? {
            type: 'message',
            id: assistant.id,
            sessionId: assistant.session_id,
            role: 'assistant'
          }
        : null
    }}
  >
    <header
      class="flex items-center justify-between text-[10px] uppercase tracking-wider mb-1
        {isStreaming ? 'text-amber-400' : 'text-slate-500'}"
    >
      <span class="flex items-center gap-2">
        {#if bulkMode && assistant}
          <input
            type="checkbox"
            class="accent-emerald-500 cursor-pointer"
            aria-label={`Select assistant message ${assistant.id}`}
            checked={isSelected(assistant.id)}
            onclick={(e) => onCheckboxClick(e, assistant!)}
            data-testid="bulk-checkbox"
            data-message-id={assistant.id}
          />
        {/if}
        <span>assistant{isStreaming ? ' · streaming' : ''}</span>
      </span>
      {#if assistant && reorgEnabled && !bulkMode}
        <div class="relative" data-reorg-menu>
          <button
            type="button"
            class="opacity-0 group-hover:opacity-100 focus:opacity-100 text-slate-400
              hover:text-slate-200 px-1"
            aria-label="Message actions"
            aria-haspopup="menu"
            aria-expanded={openMenuId === assistant.id}
            onclick={(e) => {
              e.stopPropagation();
              toggleMenu(assistant!.id);
            }}
            data-testid="message-menu-trigger"
            data-message-id={assistant.id}
          >
            ⋯
          </button>
          {#if openMenuId === assistant.id}
            <div
              class="absolute right-0 top-full mt-1 z-10 rounded border border-slate-700
                bg-slate-900 shadow-lg py-1 min-w-[10rem]"
              role="menu"
              data-testid="message-menu"
            >
              {#if onMoveMessage}
                <button
                  type="button"
                  class="block w-full text-left px-3 py-1 text-xs text-slate-200
                    hover:bg-slate-800"
                  role="menuitem"
                  onclick={() => handleMove(assistant!)}
                  data-testid="menu-move"
                >
                  Move to session…
                </button>
              {/if}
              {#if onSplitAfter}
                <button
                  type="button"
                  class="block w-full text-left px-3 py-1 text-xs text-slate-200
                    hover:bg-slate-800"
                  role="menuitem"
                  onclick={() => handleSplit(assistant!)}
                  data-testid="menu-split"
                >
                  Split here…
                </button>
              {/if}
            </div>
          {/if}
        </div>
      {/if}
    </header>
    {#if assistant}
      <CollapsibleBody
        messageId={assistant.id}
        content={assistant.content}
        highlightQuery={highlightQuery}
        disabled={isStreaming}
      />
    {:else}
      <CollapsibleBody
        messageId={null}
        content={streamingContent}
        highlightQuery={highlightQuery}
        disabled={true}
      />
      <span class="inline-block animate-pulse">▍</span>
    {/if}
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
