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
   * - Items 2.5/2.6 (Inspector core + subsections) render into the right.
   *
   * Item 2.1 (this scaffold) ships placeholder labels so the layout is
   * verifiable end-to-end and the regression test
   * `src/lib/__tests__/layout.test.ts` can assert structure.
   *
   * The center column houses the conversation header / body /
   * composer described in `docs/behavior/chat.md` §"opens an existing
   * chat"; rendering of a real conversation is item 2.3's surface.
   */
  import "../app.css";
  import type { Snippet } from "svelte";

  import { SIDEBAR_STRINGS } from "$lib/config";
  import SessionList from "$lib/components/sidebar/SessionList.svelte";
  import Conversation from "$lib/components/conversation/Conversation.svelte";

  interface Props {
    children?: Snippet;
  }

  const { children }: Props = $props();

  /**
   * The active session id — selected by clicking a row in the
   * sidebar. Kept on the layout so the sidebar (which selects) and
   * the conversation pane (which reads) live in the same reactive
   * tree. Item 2.3's conversation render reads this via the layout
   * data tree; v1 of item 2.2 just keeps the highlight wired.
   */
  let selectedSessionId = $state<string | null>(null);

  function handleSelectSession(sessionId: string): void {
    selectedSessionId = sessionId;
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
      {#if selectedSessionId !== null}
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
    <header class="app-shell__inspector-header border-b border-border p-3">
      <h2 class="font-mono text-sm text-fg-strong">Inspector</h2>
      <p class="text-xs text-fg-muted">Agent · Context · Instructions · Routing · Usage</p>
    </header>
    <nav
      class="app-shell__inspector-body p-3 text-sm text-fg-muted"
      aria-label="Inspector subsections"
    >
      <p>Inspector subsections — wired in items 2.5 + 2.6.</p>
    </nav>
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

  .app-shell__sidebar-body,
  .app-shell__inspector-body {
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
