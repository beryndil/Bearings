<script lang="ts">
  import { conversation } from '$lib/stores/conversation.svelte';
  import { sessions } from '$lib/stores/sessions.svelte';
  import { agent } from '$lib/agent.svelte';
  import * as api from '$lib/api';
  import MessageTurn from '$lib/components/MessageTurn.svelte';
  import SessionEdit from '$lib/components/SessionEdit.svelte';
  import { buildTurns } from '$lib/turns';
  import {
    connectionLabel,
    copyText,
    messagesAsMarkdown,
    nextPermissionMode,
    pressureClass
  } from '$lib/utils/conversation-ui';

  const turns = $derived(
    buildTurns({
      messages: conversation.messages,
      toolCalls: conversation.toolCalls,
      streamingActive: conversation.streamingActive,
      streamingMessageId: conversation.streamingMessageId,
      streamingThinking: conversation.streamingThinking,
      streamingText: conversation.streamingText
    })
  );

  let promptText = $state('');
  let scrollContainer: HTMLDivElement | undefined = $state();
  let editingSession = $state(false);
  let exporting = $state(false);
  let copiedMsgId = $state<string | null>(null);
  let copiedSession = $state(false);

  async function onCopyMessage(msg: api.Message) {
    if (!(await copyText(msg.content))) return;
    copiedMsgId = msg.id;
    setTimeout(() => {
      if (copiedMsgId === msg.id) copiedMsgId = null;
    }, 1500);
  }

  async function onCopySession() {
    const sid = sessions.selectedId;
    if (!sid || copiedSession) return;
    // Pull the full list so the copy isn't limited to what's paged in.
    const dump = await api.exportSession(sid);
    if (!(await copyText(messagesAsMarkdown(dump.messages)))) return;
    copiedSession = true;
    setTimeout(() => (copiedSession = false), 1500);
  }

  // Tag chips in the header. Refetch on session change and on
  // `updated_at` bumps (SessionEdit attach/detach bumps the server).
  let sessionTags = $state<api.Tag[]>([]);

  $effect(() => {
    const sid = sessions.selected?.id ?? null;
    void sessions.selected?.updated_at;
    if (!sid) {
      sessionTags = [];
      return;
    }
    api.listSessionTags(sid).then((r) => (sessionTags = r), () => {});
  });

  async function onExport() {
    const sid = sessions.selectedId;
    if (!sid || exporting) return;
    exporting = true;
    try {
      const dump = await api.exportSession(sid);
      const blob = new Blob([JSON.stringify(dump, null, 2)], {
        type: 'application/json'
      });
      const url = URL.createObjectURL(blob);
      const day = new Date().toISOString().slice(0, 10).replaceAll('-', '');
      const name = `session-${sid.slice(0, 8)}-${day}.json`;
      const a = document.createElement('a');
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      exporting = false;
    }
  }

  $effect(() => {
    void conversation.messages;
    void conversation.streamingText;
    if (scrollContainer) {
      queueMicrotask(() => {
        if (scrollContainer) scrollContainer.scrollTop = scrollContainer.scrollHeight;
      });
    }
  });

  const SCROLL_TOP_THRESHOLD = 40;

  $effect(() => {
    const el = scrollContainer;
    if (!el) return;
    async function onScroll() {
      if (!el) return;
      if (el.scrollTop > SCROLL_TOP_THRESHOLD) return;
      if (!conversation.hasMore || conversation.loadingOlder) return;
      const prevHeight = el.scrollHeight;
      await conversation.loadOlder();
      // Preserve viewport: after prepend, keep the first-previously-
      // visible message in the same screen position.
      if (el) el.scrollTop = el.scrollHeight - prevHeight;
    }
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  });

  function onSend() {
    const text = promptText.trim();
    if (!text) return;
    const modeNext = nextPermissionMode(text, agent.permissionMode);
    if (modeNext !== null) {
      agent.setPermissionMode(modeNext);
      promptText = '';
      return;
    }
    if (!agent.send(text)) return;
    promptText = '';
  }

  function onKeydown(e: KeyboardEvent) {
    // Enter sends; Shift+Enter falls through so the textarea inserts
    // a newline. Skip while the user is mid-IME composition.
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      onSend();
    }
  }

  // Document-level Esc clears an active search highlight. Scoped to
  // this component so it only binds while a session is open; the
  // textarea keeps its own Esc handling via browser defaults.
  $effect(() => {
    function onDocKey(e: KeyboardEvent) {
      if (e.key !== 'Escape') return;
      if (!conversation.highlightQuery) return;
      // Don't hijack Esc while the user is typing a prompt.
      const active = document.activeElement;
      const inTextarea = active?.tagName === 'TEXTAREA' || active?.tagName === 'INPUT';
      if (inTextarea) return;
      conversation.highlightQuery = '';
    }
    document.addEventListener('keydown', onDocKey);
    return () => document.removeEventListener('keydown', onDocKey);
  });

</script>

<SessionEdit
  bind:open={editingSession}
  sessionId={sessions.selectedId}
/>

<section class="bg-slate-900 overflow-hidden flex flex-col min-w-0">
  <header class="border-b border-slate-800 px-4 py-3 flex items-baseline justify-between">
    <div class="min-w-0">
      <h1 class="text-lg font-medium flex items-center gap-2">
        {sessions.selected?.title ?? 'Bearings'}
        {#if sessions.selected}
          <button
            type="button"
            class="text-xs text-slate-500 hover:text-slate-300"
            aria-label="Edit session"
            title="Edit title / budget"
            onclick={() => (editingSession = true)}
          >
            ✎
          </button>
          <button
            type="button"
            class="text-xs text-slate-500 hover:text-slate-300 disabled:opacity-50"
            aria-label="Export session"
            title="Download as JSON"
            onclick={onExport}
            disabled={exporting}
          >
            ⇣
          </button>
          <button
            type="button"
            class="text-xs text-slate-500 hover:text-slate-300 disabled:opacity-50"
            aria-label="Copy session to clipboard"
            title={copiedSession ? 'Copied' : 'Copy session as markdown'}
            onclick={onCopySession}
            disabled={copiedSession}
          >
            {copiedSession ? '✓' : '⎘'}
          </button>
        {/if}
      </h1>
      <p class="text-xs font-mono truncate text-slate-500">
        {#if sessions.selected}
          {sessions.selected.model} · {sessions.selected.working_dir} ·
          <span class={pressureClass(conversation.totalCost, sessions.selected.max_budget_usd)}>
            spent ${conversation.totalCost.toFixed(4)}{sessions.selected.max_budget_usd != null
              ? ` / $${sessions.selected.max_budget_usd.toFixed(2)}`
              : ''}
          </span>
          {#if sessions.selected.message_count > 0}
            · {sessions.selected.message_count} msg{sessions.selected.message_count === 1
              ? ''
              : 's'}
          {/if}
        {:else}
          select or create a session to start
        {/if}
      </p>
      {#if sessions.selected && sessionTags.length > 0}
        <ul class="flex flex-wrap gap-1 mt-1.5" aria-label="Session tags">
          {#each sessionTags as tag (tag.id)}
            <li
              class="inline-flex items-center gap-1 rounded bg-slate-800 px-1.5 py-0.5
                text-[10px] font-mono text-slate-300"
              title={tag.default_working_dir || tag.default_model
                ? `defaults: ${tag.default_working_dir ?? ''} ${tag.default_model ?? ''}`.trim()
                : tag.name}
            >
              {#if tag.pinned}
                <span class="text-amber-400" aria-hidden="true">★</span>
              {/if}
              <span>{tag.name}</span>
            </li>
          {/each}
        </ul>
      {/if}
      {#if sessions.selected?.description}
        <p class="text-xs text-slate-400 mt-1 whitespace-pre-wrap break-words">
          {sessions.selected.description}
        </p>
      {/if}
    </div>
    <div class="flex items-center gap-2">
      {#if agent.permissionMode !== 'default'}
        <button
          type="button"
          class="text-[10px] uppercase tracking-wider px-2 py-1 rounded
            bg-sky-900 text-sky-200 hover:bg-sky-800"
          onclick={() => agent.setPermissionMode('default')}
          title="Click to exit {agent.permissionMode} mode (or type /plan off)"
        >
          {agent.permissionMode}
        </button>
      {/if}
      {#if conversation.streamingActive}
        <button
          type="button"
          class="text-[10px] uppercase tracking-wider px-2 py-1 rounded
            bg-rose-900 text-rose-200 hover:bg-rose-800"
          onclick={() => agent.stop()}
          title="Stop the in-flight stream"
        >
          Stop
        </button>
      {/if}
      <span
        class="text-[10px] uppercase tracking-wider px-2 py-1 rounded
          {agent.state === 'open'
            ? 'bg-emerald-900 text-emerald-300'
            : agent.state === 'connecting'
              ? 'bg-amber-900 text-amber-300'
              : 'bg-slate-800 text-slate-400'}"
      >
        {connectionLabel(agent.state, agent.reconnectDelayMs, agent.lastCloseCode)}
      </span>
    </div>
  </header>

  {#if conversation.highlightQuery}
    <div
      class="px-4 py-1.5 bg-amber-950/40 border-b border-amber-900/40
        flex items-center justify-between text-xs"
    >
      <span class="text-amber-200">
        Matching <span class="font-mono">«{conversation.highlightQuery}»</span> · Esc to clear
      </span>
      <button
        type="button"
        class="text-amber-400 hover:text-amber-200"
        aria-label="Clear highlight"
        onclick={() => (conversation.highlightQuery = '')}
      >
        ✕
      </button>
    </div>
  {/if}

  <div bind:this={scrollContainer} class="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-4">
    {#if conversation.hasMore}
      <p class="text-[10px] text-slate-600 text-center">
        {conversation.loadingOlder ? 'Loading older…' : 'Scroll up to load older messages'}
      </p>
    {/if}
    {#if !sessions.selectedId}
      <p class="text-slate-500 text-sm">No session selected.</p>
    {:else if conversation.messages.length === 0 && !conversation.streamingActive}
      <p class="text-slate-500 text-sm">
        No messages yet. Send a prompt to start the conversation.
      </p>
    {:else}
      {#each turns as turn (turn.key)}
        <MessageTurn
          user={turn.user}
          assistant={turn.assistant}
          thinking={turn.thinking}
          toolCalls={turn.toolCalls}
          streamingContent={turn.streamingContent}
          streamingThinking={turn.streamingThinking}
          isStreaming={turn.isStreaming}
          highlightQuery={conversation.highlightQuery}
          {copiedMsgId}
          {onCopyMessage}
        />
      {/each}

      {#if conversation.error}
        <article class="rounded border border-rose-900/50 px-3 py-2 bg-rose-950/30">
          <header class="text-[10px] uppercase tracking-wider text-rose-400 mb-1">
            error
          </header>
          <pre class="text-xs text-rose-300 whitespace-pre-wrap">{conversation.error}</pre>
        </article>
      {/if}
    {/if}
  </div>

  <form
    class="border-t border-slate-800 px-4 py-3 flex gap-2 items-end"
    onsubmit={(e) => {
      e.preventDefault();
      onSend();
    }}
  >
    <textarea
      class="flex-1 rounded bg-slate-950 border border-slate-800 px-3 py-2 text-sm
        resize-none focus:outline-none focus:border-slate-600 disabled:opacity-50"
      rows="2"
      placeholder={sessions.selectedId
        ? 'Send a prompt (Enter · Shift+Enter for newline)'
        : 'Select a session first'}
      bind:value={promptText}
      onkeydown={onKeydown}
      disabled={!sessions.selectedId || agent.state !== 'open'}
    ></textarea>
    <button
      type="submit"
      class="rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-2 text-sm
        disabled:opacity-50 disabled:cursor-not-allowed"
      disabled={!sessions.selectedId || agent.state !== 'open' || !promptText.trim()}
    >
      Send
    </button>
  </form>
</section>

<style>
  :global(mark.search-mark) {
    background-color: rgb(234 179 8 / 0.35);
    color: rgb(253 224 71);
    border-radius: 0.125rem;
    padding: 0 0.125rem;
  }
</style>
