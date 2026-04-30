<script lang="ts">
  /**
   * Inspector Changes tab — Phase 5 of the v1.0.0 dashboard redesign.
   *
   * Lists every WRITE-side tool call in this session — Edit, Write,
   * NotebookEdit — derived client-side from `conversation.toolCalls`.
   * Read/Grep/Glob are excluded; this tab is about what Claude
   * *changed*, not what it looked at (Files tab covers the looking).
   *
   * For each change row we show:
   *   - the path (with `/home/<user>/...` shortened to `~/...`)
   *   - the action verb (Created / Edited / Notebook-edited)
   *   - a short content excerpt:
   *       Edit          → first line of `new_string`
   *       Write         → first line of `content`
   *       NotebookEdit  → first line of `new_source`
   *   - timestamp
   *
   * **Why no actual diff render.** The mockup shows a per-session
   * diff view; Bearings doesn't store the pre-edit content for
   * Write calls (the file existed before; Claude saw whatever was
   * on disk at write time). Edit calls do carry old_string +
   * new_string in the input, so a real inline diff IS technically
   * possible there — but rendering a diff inside the narrow
   * inspector column is bad UX, and shipping it for Edit calls only
   * (silent gap on Write) would be misleading. The honest first cut
   * is "what was changed" + a single-line sample; a richer diff
   * surface lands in a follow-up phase if Dave wants it.
   *
   * NO server endpoint. NO new schema. Pure derivation from the
   * existing tool-call stream.
   */
  import { conversation } from '$lib/stores/conversation.svelte';
  import { sessions } from '$lib/stores/sessions.svelte';
  import { formatTime } from '$lib/utils/datetime';

  type Change = {
    id: string;
    path: string;
    verb: 'Created' | 'Edited' | 'Notebook-edited';
    excerpt: string;
    at: number;
  };

  function firstLine(s: unknown): string {
    if (typeof s !== 'string') return '';
    const trimmed = s.trimStart();
    const nl = trimmed.indexOf('\n');
    return (nl === -1 ? trimmed : trimmed.slice(0, nl)).slice(0, 120);
  }

  function homeShorten(path: string): string {
    const home = '/home/';
    if (path.startsWith(home)) {
      const rest = path.slice(home.length);
      const slash = rest.indexOf('/');
      if (slash !== -1) return '~' + rest.slice(slash);
    }
    return path;
  }

  function changeFromCall(call: {
    id: string;
    name: string;
    input: Record<string, unknown>;
    startedAt: number;
  }): Change | null {
    if (call.name === 'Edit') {
      const path = call.input.file_path;
      if (typeof path !== 'string') return null;
      return {
        id: call.id,
        path,
        verb: 'Edited',
        excerpt: firstLine(call.input.new_string),
        at: call.startedAt,
      };
    }
    if (call.name === 'Write') {
      const path = call.input.file_path;
      if (typeof path !== 'string') return null;
      return {
        id: call.id,
        path,
        verb: 'Created',
        excerpt: firstLine(call.input.content),
        at: call.startedAt,
      };
    }
    if (call.name === 'NotebookEdit') {
      const path = call.input.notebook_path;
      if (typeof path !== 'string') return null;
      return {
        id: call.id,
        path,
        verb: 'Notebook-edited',
        excerpt: firstLine(call.input.new_source),
        at: call.startedAt,
      };
    }
    return null;
  }

  let changes = $derived.by<Change[]>(() => {
    const out: Change[] = [];
    for (const call of conversation.toolCalls) {
      const c = changeFromCall(call);
      if (c) out.push(c);
    }
    return out.sort((a, b) => b.at - a.at);
  });

  function verbClasses(verb: Change['verb']): string {
    switch (verb) {
      case 'Created':
        return 'bg-emerald-900/60 text-emerald-300';
      case 'Edited':
        return 'bg-amber-900/60 text-amber-300';
      case 'Notebook-edited':
        return 'bg-indigo-900/60 text-indigo-300';
    }
  }
</script>

<div class="p-4" data-testid="inspector-tab-changes-content">
  {#if !sessions.selected}
    <p class="text-sm text-slate-500">Select a session to see the changes Claude made.</p>
  {:else if changes.length === 0}
    <div
      class="rounded-md border border-slate-800 bg-slate-950/40 px-3 py-3"
      data-testid="changes-empty"
    >
      <p class="font-medium text-slate-300">No changes yet</p>
      <p class="mt-1 text-xs text-slate-500">
        Edit / Write / NotebookEdit tool calls in this session will show up here, with the affected
        path, action, and a single-line excerpt of the new content.
      </p>
    </div>
  {:else}
    <header class="mb-2 flex items-baseline justify-between">
      <h3 class="text-[10px] font-medium uppercase tracking-wider text-slate-500">Changes</h3>
      <span class="font-mono text-[11px] text-slate-500">
        {changes.length} change{changes.length === 1 ? '' : 's'}
      </span>
    </header>
    <ul class="flex flex-col gap-1.5" data-testid="changes-list">
      {#each changes as change (change.id)}
        <li
          class="rounded border border-slate-800 bg-slate-950/40 px-2 py-1.5"
          data-testid="change-row"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="truncate font-mono text-[11px] text-slate-300" title={change.path}
              >{homeShorten(change.path)}</span
            >
            <span
              class="shrink-0 rounded px-1.5 py-0.5 text-[9px] uppercase tracking-wider
                {verbClasses(change.verb)}"
            >
              {change.verb}
            </span>
          </div>
          {#if change.excerpt}
            <pre class="mt-1 truncate font-mono text-[10px] text-slate-500">{change.excerpt}</pre>
          {/if}
          <time
            class="mt-0.5 block font-mono text-[10px] text-slate-600"
            datetime={new Date(change.at).toISOString()}
          >
            {formatTime(new Date(change.at).toISOString())}
          </time>
        </li>
      {/each}
    </ul>
  {/if}
</div>
