<script lang="ts">
  import { goto } from '$app/navigation';
  import { sessions } from '$lib/stores/sessions.svelte';
  import { sessionSelection } from '$lib/stores/session_selection.svelte';
  import { tags } from '$lib/stores/tags.svelte';
  import { uiActions } from '$lib/stores/ui_actions.svelte';
  import { agent } from '$lib/agent.svelte';
  import * as api from '$lib/api';
  import type { ContextTarget } from '$lib/context-menu/types';
  import DataView from '$lib/components/DataView.svelte';
  import NewSessionForm from '$lib/components/NewSessionForm.svelte';
  import PendingOpsBadge from '$lib/components/pending/PendingOpsBadge.svelte';
  import Settings from '$lib/components/Settings.svelte';
  import SidebarSearch from '$lib/components/SidebarSearch.svelte';
  import TagFilterPanel from '$lib/components/TagFilterPanel.svelte';
  import TemplatePicker from '$lib/components/TemplatePicker.svelte';
  import NewSessionPill from '$lib/components/sidebar/NewSessionPill.svelte';
  import SidebarBrand from '$lib/components/sidebar/SidebarBrand.svelte';
  import SidebarNav from '$lib/components/sidebar/SidebarNav.svelte';
  import SystemStatusCard from '$lib/components/sidebar/SystemStatusCard.svelte';
  import UserIdentityBlock from '$lib/components/sidebar/UserIdentityBlock.svelte';
  import SessionListClosedGroup from './SessionListClosedGroup.svelte';
  import SessionListItem from './SessionListItem.svelte';
  import { indicatorState } from './sessionListHelpers.js';
  import { scrollBehavior } from '$lib/utils/motion';

  const CONFIRM_TIMEOUT_MS = 3_000;

  // Deep-link entry: a fresh page load with `?settings=<id>` should
  // open the Settings dialog and land on the named section. The shell
  // (SettingsShell.svelte) reads the param itself for the initial
  // `activeId`; this just flips the shared `uiActions.settingsOpen`
  // flag so the URL anchor works as a real shareable deep-link, not
  // just a mid-session "remember which pane I was on" sticky.
  // Phase 2c lifted Settings open-state out of per-component locals
  // and into `uiActions` so the sidebar nav rail (gear) and the
  // user-identity avatar block can both flip the same flag.
  $effect(() => {
    if (typeof window === 'undefined') return;
    const params = new URL(window.location.href).searchParams;
    if (params.has('settings')) uiActions.settingsOpen = true;
  });

  let importInput: HTMLInputElement | undefined = $state();
  let importError = $state<string | null>(null);
  let importProgress = $state<{ done: number; total: number } | null>(null);
  let dragging = $state(false);

  let searchQuery = $state('');

  // Collapsed state for the bottom "Closed (N)" group. Local-only by
  // design — a per-browser sticky preference would be a separate
  // prefs-store addition; resetting to collapsed each page load keeps
  // the sidebar quiet on boot.
  let closedCollapsed = $state(true);

  // Bound to the scrollable middle band below (the Recent Sessions
  // list area) so the scroll-to-top effect can pull the just-bumped
  // selected session into view. Phase 2c split the sidebar into three
  // zones — top bands (brand/pill/nav/tools) and bottom bands
  // (system-status/user-identity) are fixed; only this middle zone
  // scrolls — so this ref now points at the middle div, not the
  // outer aside. (Pre-2c, the aside itself was the scroller.)
  let asideEl: HTMLElement | undefined = $state();
  // Baseline so the mount-time run of the effect (which reads the
  // current tick) doesn't fire a gratuitous scroll. Only real tick
  // increments from this point forward trigger the scroll. `?.scrollTo?.`
  // also shrugs off jsdom, which doesn't implement it.
  let lastSeenScrollTick = sessions.scrollTick;
  $effect(() => {
    const t = sessions.scrollTick;
    if (t === lastSeenScrollTick) return;
    lastSeenScrollTick = t;
    // `scrollBehavior()` resolves to 'auto' under `prefers-reduced-motion:
    // reduce` so the bump-to-top still happens but as an instant snap.
    asideEl?.scrollTo?.({ top: 0, behavior: scrollBehavior() });
  });

  async function importOne(file: File): Promise<api.Session> {
    const text = await file.text();
    const payload = JSON.parse(text);
    return api.importSession(payload);
  }

  async function importFromFiles(files: File[]) {
    if (files.length === 0) return;
    importError = null;
    const failures: { name: string; error: string }[] = [];
    const created: api.Session[] = [];
    importProgress = { done: 0, total: files.length };
    for (const file of files) {
      try {
        created.push(await importOne(file));
      } catch (err) {
        failures.push({
          name: file.name,
          error: err instanceof Error ? err.message : String(err),
        });
      }
      importProgress = { done: created.length + failures.length, total: files.length };
    }
    importProgress = null;

    // Prepend everything that landed — last-imported ends up on top.
    if (created.length > 0) {
      const keep = sessions.list.filter((s) => !created.some((c) => c.id === s.id));
      sessions.list = [...created.reverse(), ...keep];
      const focus = created[0]; // the last one imported (after reverse)
      // Navigate to the freshly-imported session — the URL→state sync
      // in /sessions/[id]/+page.svelte calls `select` and
      // `agent.connect` once the route mounts.
      void goto(`/sessions/${encodeURIComponent(focus.id)}`);
    }
    if (failures.length > 0) {
      importError = failures.map((f) => `${f.name}: ${f.error}`).join('; ');
    }
  }

  async function onImportFile(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = '';
    if (files.length > 0) await importFromFiles(files);
  }

  function hasFiles(e: DragEvent): boolean {
    return e.dataTransfer?.types.includes('Files') ?? false;
  }

  function onDragEnter(e: DragEvent) {
    if (hasFiles(e)) dragging = true;
  }
  function onDragOver(e: DragEvent) {
    // preventDefault so the browser allows a drop; without this the
    // drop event never fires.
    if (hasFiles(e)) e.preventDefault();
  }
  function onDragLeave(e: DragEvent) {
    // Only clear when leaving the aside entirely, not when crossing
    // into a child element (relatedTarget outside the current node).
    const related = e.relatedTarget as Node | null;
    if (!related || !(e.currentTarget as Node).contains(related)) {
      dragging = false;
    }
  }
  async function onDrop(e: DragEvent) {
    e.preventDefault();
    dragging = false;
    const files = Array.from(e.dataTransfer?.files ?? []);
    if (files.length > 0) await importFromFiles(files);
  }

  const confirm = $state<{ id: string | null }>({ id: null });
  let confirmTimer: ReturnType<typeof setTimeout> | null = null;

  function clearConfirm() {
    if (confirmTimer !== null) {
      clearTimeout(confirmTimer);
      confirmTimer = null;
    }
    confirm.id = null;
  }

  const rename = $state<{ id: string | null; draft: string }>({ id: null, draft: '' });

  function startRename(
    e: MouseEvent,
    session: { id: string; title: string | null; model: string }
  ) {
    e.stopPropagation();
    rename.id = session.id;
    rename.draft = session.title ?? '';
  }

  async function commitRename() {
    if (rename.id === null) return;
    const id = rename.id;
    const draft = rename.draft.trim();
    rename.id = null;
    rename.draft = '';
    await sessions.update(id, { title: draft === '' ? null : draft });
  }

  function cancelRename() {
    rename.id = null;
    rename.draft = '';
  }

  // Boot (auth + session refresh) is owned by +page.svelte so the auth
  // gate can block API calls until a token is supplied.

  // Re-fetch the session list whenever any filter axis changes. Initial
  // boot in +page.svelte happens before the first effect settles, so
  // this only fires on subsequent filter edits. The key encodes both
  // axes — general-tag selection and severity selection — so adding/
  // removing either triggers a refresh without a user also having to
  // touch the other axis. General-tag combination is always OR now
  // (v0.7.4), so there's no separate `mode` component to key off of.
  let filterKey = $derived(`${tags.selected.join(',')}|${tags.selectedSeverity.join(',')}`);
  let lastAppliedKey = '';
  $effect(() => {
    const key = filterKey;
    if (key === lastAppliedKey) return;
    lastAppliedKey = key;
    sessions.refresh(tags.filter);
  });

  // v0.7.4: severity counts in the sidebar are scoped to the current
  // general-tag selection, so each change to `tags.selected` needs a
  // tag refresh to pull the updated counts from the server. Severity
  // selection doesn't feed into this — severity counts are independent
  // of severity selection (the count would otherwise collapse to the
  // sum of selected severities, which is meaningless). Keyed off the
  // general selection only to avoid a wasteful refresh when severity
  // alone toggles.
  let generalSelectionKey = $derived(tags.selected.join(','));
  let lastGeneralKey = '';
  $effect(() => {
    const key = generalSelectionKey;
    if (key === lastGeneralKey) return;
    lastGeneralKey = key;
    void tags.refresh();
  });

  /** Ordered ids of every session currently rendered in the sidebar —
   * `openList` first, then `closedList`. Used as the range-selection
   * axis for Shift-click so anchors span the visual order the user
   * sees. Re-derived every tick so filter changes keep the range in
   * sync. */
  let orderedVisibleIds = $derived([
    ...sessions.openList.map((s) => s.id),
    ...sessions.closedList.map((s) => s.id),
  ]);

  /** Resolve the context-menu target for a right-clicked session row.
   * If the row is part of the active multi-selection, dispatch the
   * aggregate `multi_select` target — otherwise stay on the per-session
   * menu. Rows right-clicked while a disjoint selection exists keep
   * their single-session menu (the selection belongs to other rows). */
  function rowTarget(id: string): ContextTarget {
    if (sessionSelection.hasSelection && sessionSelection.ids.has(id)) {
      return { type: 'multi_select', ids: [...sessionSelection.ids] };
    }
    return { type: 'session', id };
  }

  async function onSelect(id: string, e: MouseEvent) {
    // Cmd/Ctrl+click toggles membership without touching the navigated
    // session. The sidebar's focused session stays put so Daisy can
    // keep reading while she composes a batch.
    if (e.metaKey || e.ctrlKey) {
      e.preventDefault();
      sessionSelection.toggle(id);
      return;
    }
    // Shift+click grows the selection inclusively from the anchor.
    // Fall back to `toggle` inside selectRange when no anchor is set.
    if (e.shiftKey) {
      e.preventDefault();
      sessionSelection.selectRange(id, orderedVisibleIds);
      return;
    }
    // Plain click: collapse any multi-selection, then navigate. The
    // URL is the source of truth — `goto` triggers
    // `(app)/sessions/[id]/+page.svelte`, which mirrors `params.id`
    // into `sessions.selectedId`, fires `markViewed`, and connects the
    // agent. Skipping the goto for the no-op case (clicking the
    // already-selected row) keeps the browser history clean and avoids
    // a needless WebSocket re-handshake.
    if (sessionSelection.hasSelection) sessionSelection.clear();
    if (sessions.selectedId === id) return;
    void goto(`/sessions/${encodeURIComponent(id)}`);
  }

  async function onDelete(e: MouseEvent, id: string) {
    e.stopPropagation();
    if (confirm.id !== id) {
      confirm.id = id;
      if (confirmTimer !== null) clearTimeout(confirmTimer);
      confirmTimer = setTimeout(clearConfirm, CONFIRM_TIMEOUT_MS);
      return;
    }
    clearConfirm();
    if (agent.sessionId === id) agent.close();
    await sessions.remove(id);
  }
</script>

<Settings bind:open={uiActions.settingsOpen} />

<aside
  class="relative flex h-full flex-col gap-2 overflow-hidden border-r
    border-slate-800 bg-slate-900 p-2 {dragging ? 'ring-2 ring-inset ring-emerald-500/60' : ''}"
  ondragenter={onDragEnter}
  ondragover={onDragOver}
  ondragleave={onDragLeave}
  ondrop={onDrop}
>
  <!-- Phase 2c sidebar bands (top): brand → big New Session pill →
       primary navigation rail. The old SessionListHeader toolbar
       (small +New / settings / import / vault buttons) split into
       these bands plus the small "Tools" row below; Settings moved
       into the nav rail's gear, so the modal opens from there now. -->
  <SidebarBrand />
  <NewSessionPill />
  <SidebarNav />

  <NewSessionForm bind:open={uiActions.newSessionOpen} />

  <!-- Compact tools row — preserves the four toolbar actions that
       didn't get a nav slot (Import, Pending count, Templates, Vault).
       Smaller and lower than the original SessionListHeader so it
       reads as secondary; the primary actions are the New Session
       pill and the nav rail. -->
  <div
    class="flex items-center justify-between gap-1 px-1 text-slate-400"
    data-testid="sidebar-tools"
  >
    <span class="text-[10px] uppercase tracking-wider text-slate-500">Tools</span>
    <div class="flex items-center gap-1">
      <button
        type="button"
        class="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] hover:bg-slate-700"
        aria-label="Import session from JSON"
        title="Import a session.json file"
        onclick={() => importInput?.click()}
      >
        ⇡
      </button>
      <input
        type="file"
        accept="application/json,.json"
        multiple
        class="hidden"
        bind:this={importInput}
        onchange={onImportFile}
      />
      <PendingOpsBadge />
      <TemplatePicker />
      <a
        href="/vault"
        class="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] hover:bg-slate-700"
        aria-label="Open vault (plans + TODOs)"
        title="Open vault — browse plans and TODO.md files"
        data-testid="vault-link"
      >
        📚
      </a>
    </div>
  </div>

  {#if dragging}
    <div
      class="pointer-events-none absolute inset-2 z-10 flex items-center
        justify-center rounded border-2 border-dashed border-emerald-500/70 bg-slate-950/60"
    >
      <p class="text-sm text-emerald-300">Drop session JSON to import</p>
    </div>
  {/if}

  <!-- Recent Sessions band — heading, search, tag filter, then the
       session list itself. The old layout had Search above NewSessionForm
       and the tag filter immediately under; reordering puts the
       sessions surface in one labeled block under the rail.
       Wrapped in `flex-1 overflow-y-auto` so this is the only zone
       that scrolls — the top brand/pill/nav/tools and bottom system-
       status/user-identity bands stay pinned. -->
  <h3
    class="mt-1 shrink-0 px-1 text-[10px] font-medium uppercase tracking-wider text-slate-500"
    data-testid="recent-sessions-heading"
  >
    Recent Sessions
  </h3>

  <div bind:this={asideEl} class="flex flex-1 flex-col gap-2 overflow-y-auto">
    <SidebarSearch bind:query={searchQuery} />

    {#if importProgress}
      <p class="text-xs text-emerald-300">
        Importing {importProgress.done} of {importProgress.total}…
      </p>
    {/if}
    {#if importError}
      <p class="text-xs text-rose-400">import: {importError}</p>
    {/if}

    {#if !searchQuery.trim()}
      <TagFilterPanel />
    {/if}

    {#snippet sessionRow(session: api.Session)}
      <SessionListItem
        {session}
        selected={sessions.selectedId === session.id}
        bulkSelected={sessionSelection.ids.has(session.id)}
        indicator={indicatorState(session, sessions.awaiting, sessions.running)}
        confirming={confirm.id === session.id}
        renaming={rename.id === session.id}
        renameDraft={rename.draft}
        allTags={tags.list}
        contextTarget={rowTarget(session.id)}
        {onSelect}
        {onDelete}
        onStartRename={startRename}
        onCommitRename={commitRename}
        onCancelRename={cancelRename}
        onRenameDraftChange={(draft) => (rename.draft = draft)}
      />
    {/snippet}

    {#if searchQuery.trim()}
      <!-- SidebarSearch renders its own results list above. -->
    {:else}
      <!-- §9 wrapper: skeleton on first load, error+retry on fetch
         failure, "No sessions yet." on empty. The retry path calls
         `sessions.refresh(tags.filter)` so the same filter the user
         last applied is re-tried — otherwise a retry would silently
         drop their tag selection. -->
      <DataView
        loading={sessions.loading && sessions.list.length === 0}
        error={sessions.error}
        isEmpty={sessions.list.length === 0}
        onRetry={() => sessions.refresh(tags.filter)}
        emptyLabel="No sessions yet."
        loadingLabel="Loading sessions"
      >
        {#if sessions.openList.length > 0}
          <ul class="flex flex-col gap-1">
            {#each sessions.openList as session (session.id)}
              {@render sessionRow(session)}
            {/each}
          </ul>
        {:else}
          <p class="text-sm text-slate-500">No open sessions.</p>
        {/if}
      </DataView>

      {#if sessionSelection.hasSelection}
        <!-- Selection footer: sticky reminder that bulk mode is active.
           The real bulk ops fire from the right-click menu on any
           selected row (dispatches the `multi_select` target). -->
        <div
          class="mt-2 flex items-center justify-between gap-2 border-t
          border-emerald-700/40 pt-2 text-xs"
          data-testid="session-bulk-bar"
        >
          <span class="text-emerald-300">
            {sessionSelection.size} selected
          </span>
          <span class="text-slate-500">Right-click for actions</span>
          <button
            type="button"
            class="rounded bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300
            hover:bg-slate-700"
            onclick={() => sessionSelection.clear()}
            data-testid="session-bulk-clear"
          >
            Clear
          </button>
        </div>
      {/if}

      {#if sessions.closedList.length > 0}
        <SessionListClosedGroup
          closedList={sessions.closedList}
          collapsed={closedCollapsed}
          onToggle={() => (closedCollapsed = !closedCollapsed)}
          {sessionRow}
        />
      {/if}
    {/if}
  </div>
  <!-- /Recent Sessions scroll zone -->

  <!-- Phase 2c sidebar bands (bottom): system-status card pinned
       above the user-identity block. `shrink-0` so they keep their
       own height regardless of how many sessions are scrolling
       above; the middle scroll zone (Recent Sessions) takes all
       remaining height via `flex-1`. -->
  <div class="flex shrink-0 flex-col gap-2 pt-1">
    <SystemStatusCard />
    <UserIdentityBlock />
  </div>
</aside>
