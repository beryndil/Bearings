<script lang="ts">
  /**
   * Bearings app shell.
   *
   * Three-column layout per `docs/behavior/chat.md`:
   *
   *   ┌────────────┬──────────────────────────┬────────────┐
   *   │  Sidebar   │   Main conversation pane │ Inspector  │
   *   │  (left)    │   (center)               │ (right)    │
   *   └────────────┴──────────────────────────┴────────────┘
   *
   * The columns are SvelteKit `<slot>`-style named regions so each
   * downstream item plugs into the right column without touching the
   * shell:
   *
   * - Item 2.2 (sidebar + tag filtering) renders into the left column.
   * - Item 2.3 (Conversation + streaming) renders into the center.
   * - Item 2.5 (Inspector core + Agent/Context/Instructions) renders
   *   into the right column; item 2.6 plugs Routing/Usage tabs into
   *   the same shell without restructuring it.
   *
   * The center column houses the conversation header / body /
   * composer described in `docs/behavior/chat.md` §"opens an existing
   * chat"; rendering of a real conversation is item 2.3's surface.
   */
  import "../app.css";
  import type { Snippet } from "svelte";

  import { SESSION_KIND_CHECKLIST, SIDEBAR_STRINGS } from "$lib/config";
  import SessionList from "$lib/components/sidebar/SessionList.svelte";
  import Conversation from "$lib/components/conversation/Conversation.svelte";
  import ChecklistView from "$lib/components/checklist/ChecklistView.svelte";
  import Inspector from "$lib/components/inspector/Inspector.svelte";
  import { sessionsStore } from "$lib/stores/sessions.svelte";
  import { inspectorStore, setActiveSession } from "$lib/stores/inspector.svelte";

  interface Props {
    children?: Snippet;
  }

  const { children }: Props = $props();

  /**
   * The active session id is owned by the inspector store so the
   * sidebar (which selects), the conversation pane (which reads the
   * messages), and the inspector pane (which reads the session row)
   * all observe the same value. The local mirror below is purely for
   * the conversation prop wiring; mutation goes through
   * :func:`setActiveSession` so the store stays the source of truth.
   */
  const selectedSessionId = $derived(inspectorStore.activeSessionId);

  /**
   * Look up the active session in the sessions cache so the inspector
   * can render its row without an extra fetch. ``undefined`` (sidebar
   * has a selection but the row isn't loaded yet) is mapped to
   * ``null`` here — the inspector treats both as "render the empty
   * state" per its empty-session branch.
   */
  const activeSession = $derived(
    selectedSessionId === null
      ? null
      : (sessionsStore.sessions.find((row) => row.id === selectedSessionId) ?? null),
  );

  function handleSelectSession(sessionId: string): void {
    setActiveSession(sessionId);
  }
</script>

<div class="app-shell" data-testid="app-shell">
  <aside
    class="app-shell__sidebar border-r border-border bg-surface-1"
    data-testid="app-shell-sidebar"
    aria-label="Sessions sidebar"
  >
    <header class="app-shell__sidebar-header border-b border-border p-3">
      <h1 class="font-mono text-sm text-fg-strong">{SIDEBAR_STRINGS.heading}</h1>
      <p class="text-xs text-fg-muted">{SIDEBAR_STRINGS.versionTag}</p>
    </header>
    <div class="app-shell__sidebar-body" data-testid="app-shell-sidebar-body">
      <SessionList {selectedSessionId} onSelect={handleSelectSession} />
    </div>
  </aside>

  <main
    class="app-shell__main bg-surface-0"
    data-testid="app-shell-main"
    aria-label="Conversation pane"
  >
    <header
      class="app-shell__main-header border-b border-border p-3"
      data-testid="app-shell-main-header"
    >
      <p class="text-sm text-fg-muted">
        Conversation header — model dropdown, quota bars, paired-checklist breadcrumb (item 2.3).
      </p>
    </header>
    <section
      class="app-shell__main-body text-fg"
      data-testid="app-shell-main-body"
      aria-label="Conversation body"
    >
      {#if selectedSessionId !== null && activeSession?.kind === SESSION_KIND_CHECKLIST}
        <ChecklistView
          checklistId={selectedSessionId}
          availableChats={sessionsStore.sessions.filter(
            (row) => row.kind !== SESSION_KIND_CHECKLIST && row.closed_at === null,
          )}
          onSelectChat={handleSelectSession}
        />
      {:else if selectedSessionId !== null}
        <Conversation sessionId={selectedSessionId} />
      {:else if children}
        {@render children()}
      {:else}
        <p class="p-4 text-fg-muted">No session selected.</p>
      {/if}
    </section>
    <footer
      class="app-shell__main-composer border-t border-border bg-surface-1 p-3"
      data-testid="app-shell-main-composer"
    >
      <p class="text-sm text-fg-muted">Composer — multi-line input + send (item 2.3).</p>
    </footer>
  </main>

  <aside
    class="app-shell__inspector border-l border-border bg-surface-1"
    data-testid="app-shell-inspector"
    aria-label="Inspector"
  >
    <Inspector session={activeSession} />
  </aside>
</div>

<style>
  /*
   * The grid is the only piece that has to hold across themes —
   * everything else uses Tailwind utility classes so theme switches
   * (item 2.9) re-tint the shell synchronously.
   */
  .app-shell {
    display: grid;
    grid-template-columns: 16rem minmax(0, 1fr) 20rem;
    height: 100vh;
    width: 100vw;
    overflow: hidden;
  }

  .app-shell__sidebar,
  .app-shell__inspector {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .app-shell__sidebar-body {
    flex: 1;
    overflow-y: auto;
  }

  .app-shell__main {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
    overflow: hidden;
  }

  .app-shell__main-body {
    overflow-y: auto;
  }
</style>
