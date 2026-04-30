<script lang="ts">
  /**
   * Inspector Files tab — Phase 5 of the v1.0.0 dashboard redesign.
   *
   * Lists every distinct file path the agent has touched in this
   * session, derived client-side from `conversation.toolCalls`. The
   * mockup framed this surface as the per-session "what files did
   * Claude work on?" answer; we honor that without inventing new
   * server tracking — the tool-call list already carries the data,
   * we just regroup it.
   *
   * Path extraction reads three input keys per Claude Code tool:
   *
   *   Read / Write / Edit            → `input.file_path`
   *   NotebookEdit                   → `input.notebook_path`
   *   Grep (when scoped to a file)   → `input.path`
   *
   * Glob and Bash carry no specific file — they're omitted. Tools
   * we don't recognize get a defensive `input.file_path ?? .path`
   * fallback so MCP / custom tools that follow the convention land
   * on the list automatically.
   *
   * Each path appears once with: total touch count, the last action
   * verb (Read / Write / Edit / etc.), and the time of the most
   * recent touch. Sorted most-recent first.
   *
   * NO server endpoint. NO new schema. The Phase 5 mockup vision of
   * a working_dir TREE — separate from "files Claude touched" — is
   * deferred; trees need a directory-walker endpoint and a
   * collapsible-tree component, both honest-sized projects in
   * themselves.
   */
  import { conversation } from '$lib/stores/conversation.svelte';
  import { sessions } from '$lib/stores/sessions.svelte';
  import { formatTime } from '$lib/utils/datetime';

  type FileTouch = {
    path: string;
    touches: number;
    lastTool: string;
    lastAt: number; // Unix ms epoch
  };

  function extractPath(name: string, input: Record<string, unknown>): string | null {
    if (name === 'NotebookEdit' && typeof input.notebook_path === 'string') {
      return input.notebook_path;
    }
    if (typeof input.file_path === 'string') return input.file_path;
    // Grep with `path` scope, plus defensive fallback for MCP/custom
    // tools that adopt the same convention.
    if (typeof input.path === 'string') return input.path;
    return null;
  }

  /** Compress `/home/<user>/...` paths to `~/...` so the rows fit
   * in the narrow inspector column without wrapping mid-segment. */
  function homeShorten(path: string): string {
    const home = '/home/';
    if (path.startsWith(home)) {
      const rest = path.slice(home.length);
      const slash = rest.indexOf('/');
      if (slash !== -1) return '~' + rest.slice(slash);
    }
    return path;
  }

  let touches = $derived.by<FileTouch[]>(() => {
    const byPath = new Map<string, FileTouch>();
    for (const call of conversation.toolCalls) {
      const path = extractPath(call.name, call.input);
      if (!path) continue;
      const prev = byPath.get(path);
      if (prev) {
        prev.touches += 1;
        if (call.startedAt > prev.lastAt) {
          prev.lastAt = call.startedAt;
          prev.lastTool = call.name;
        }
      } else {
        byPath.set(path, {
          path,
          touches: 1,
          lastTool: call.name,
          lastAt: call.startedAt,
        });
      }
    }
    return [...byPath.values()].sort((a, b) => b.lastAt - a.lastAt);
  });
</script>

<div class="p-4" data-testid="inspector-tab-files-content">
  {#if !sessions.selected}
    <p class="text-sm text-slate-500">Select a session to see the files Claude touched.</p>
  {:else if touches.length === 0}
    <div
      class="rounded-md border border-slate-800 bg-slate-950/40 px-3 py-3"
      data-testid="files-empty"
    >
      <p class="font-medium text-slate-300">No files touched yet</p>
      <p class="mt-1 text-xs text-slate-500">
        Read / Write / Edit / NotebookEdit / Grep tool calls in this session will show up here,
        grouped by path with their most-recent touch on top.
      </p>
    </div>
  {:else}
    <header class="mb-2 flex items-baseline justify-between">
      <h3 class="text-[10px] font-medium uppercase tracking-wider text-slate-500">Files Touched</h3>
      <span class="font-mono text-[11px] text-slate-500">
        {touches.length} file{touches.length === 1 ? '' : 's'}
      </span>
    </header>
    <ul class="flex flex-col gap-1.5" data-testid="files-list">
      {#each touches as t (t.path)}
        <li
          class="rounded border border-slate-800 bg-slate-950/40 px-2 py-1.5"
          title={t.path}
          data-testid="file-row"
        >
          <div class="truncate font-mono text-[11px] text-slate-300">{homeShorten(t.path)}</div>
          <div class="mt-0.5 flex items-baseline justify-between gap-2 text-[10px]">
            <span class="text-slate-500">
              {t.lastTool}{#if t.touches > 1}
                · ×{t.touches}{/if}
            </span>
            <time class="font-mono text-slate-600" datetime={new Date(t.lastAt).toISOString()}>
              {formatTime(new Date(t.lastAt).toISOString())}
            </time>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</div>
