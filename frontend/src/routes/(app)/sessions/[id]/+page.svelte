<script lang="ts">
  /**
   * URL-bound session view. The route param `id` is the source of truth
   * for which session is selected — clicking a sidebar row navigates
   * here, the back/forward buttons swap the URL, and a direct paste of
   * `/sessions/<id>` lands on the right session.
   *
   * Responsibilities:
   *  1. Sync `params.id` into `sessions.selectedId` whenever it differs.
   *     Skipping the no-op case avoids tearing down and re-establishing
   *     the agent WebSocket on a re-render that wasn't a real change.
   *  2. Drive `agent.connect(id)` for the same id, again gated on
   *     `agent.sessionId !== id` so a passive re-render (e.g. layout
   *     resize) doesn't reconnect.
   *  3. Stamp `last_viewed_at` so the amber "finished but unviewed"
   *     dot clears for the session the user just landed on.
   *  4. Render the appropriate main pane — `ChecklistView` for
   *     `kind === 'checklist'`, `Conversation` otherwise.
   *
   * The shell (sidebar, inspector, modals) lives in `(app)/+layout.svelte`
   * so navigating between sessions doesn't unmount it. Only the middle
   * grid cell — `Conversation` vs `ChecklistView` — is owned by this page.
   */
  import { untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import ChecklistView from '$lib/components/ChecklistView.svelte';
  import Conversation from '$lib/components/Conversation.svelte';
  import { agent } from '$lib/agent.svelte';
  import { sessions } from '$lib/stores/sessions.svelte';

  // `params.id` is reactive via the page store; reading it inside the
  // $derived keeps the URL→state effect tied to actual route changes.
  const sessionId = $derived($page.params.id);

  // URL → store sync. Single source-of-truth: the URL drives selection.
  // Re-runs every time `params.id` changes (mount, browser
  // back/forward, in-app navigation). The body is wrapped in
  // `untrack` so the effect's dependency set stays exactly
  // `{ sessionId }` — without it, calling `sessions.markViewed(id)`
  // would synchronously read+write `sessions.list` and re-fire the
  // effect in a tight loop.
  $effect(() => {
    const id = sessionId;
    if (!id) return;
    untrack(() => {
      if (sessions.selectedId !== id) {
        sessions.select(id);
      }
      // markViewed is optimistic locally + best-effort over the wire
      // — a failure is silently tolerated (the next user interaction
      // or poll re-stamps it). Fire-and-forget so the URL→state path
      // stays synchronous.
      void sessions.markViewed(id);
      if (agent.sessionId !== id) {
        void agent.connect(id);
      }
    });
  });

  // Session-no-longer-exists guard: a direct URL paste to a deleted
  // session, or a deletion that lands while viewing, should bounce
  // the user to the empty state rather than render a permanent
  // loading pane against a phantom selection. Gated on `!loading` so
  // the initial boot — when `list` is briefly empty — doesn't bounce
  // a legitimately-loading session away. Re-runs reactively on list
  // changes (so a deletion-while-viewing bounces) — that's the one
  // case where the effect IS supposed to be reactive on `list`.
  $effect(() => {
    const id = sessionId;
    if (!id) return;
    if (sessions.loading) return;
    if (sessions.error) return;
    if (sessions.list.length === 0) return;
    if (sessions.list.some((s) => s.id === id)) return;
    void goto('/', { replaceState: true });
  });
</script>

{#if sessions.selected?.kind === 'checklist'}
  <ChecklistView />
{:else}
  <Conversation />
{/if}
