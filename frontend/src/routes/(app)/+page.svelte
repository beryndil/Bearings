<script lang="ts">
  /**
   * Root `/` route. Three behaviors, in order:
   *
   *  1. Backward-compat: if the URL carries `?session=<id>`, redirect
   *     to `/sessions/<id>` so old bookmarks still land on their
   *     session under the new path-based scheme.
   *  2. Reload-preservation fallback: if the user lands on `/` with a
   *     remembered last-selection in localStorage AND that session is
   *     still in the open list, redirect to `/sessions/<remembered>`.
   *     This keeps the "open the app, see what I was last looking at"
   *     reflex working when no URL was supplied (e.g. typing the bare
   *     host in the address bar).
   *  3. Otherwise: render the empty-state pane. The user picks a
   *     session from the sidebar; clicking navigates to its URL.
   *
   * The shell (sidebar / inspector / modals) is rendered by
   * `(app)/+layout.svelte`; this page owns only the middle grid cell.
   */
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { sessions } from '$lib/stores/sessions.svelte';

  const REMEMBERED_KEY = 'bearings:selectedSessionId';

  function readRememberedId(): string | null {
    if (typeof localStorage === 'undefined') return null;
    try {
      return localStorage.getItem(REMEMBERED_KEY);
    } catch {
      return null;
    }
  }

  // Snapshotted at component setup, BEFORE any $effect runs. Used by
  // the redirect logic below to distinguish "fresh page load with no
  // URL deep-link" (selectedId is null because nothing was set)
  // from "user just navigated /sessions/abc → /" (selectedId is still
  // 'abc' from the dynamic route's last set). The first case should
  // restore the remembered session; the second case must not bounce
  // the user back to where they explicitly left.
  const enteredWithSelection = sessions.selectedId !== null;

  // 1. URL = `/` means "no selection." Clear `selectedId` on mount so
  //    a user navigating /sessions/abc → / doesn't carry the stale
  //    'abc' forward (the dynamic-route page sets selectedId on its
  //    own mount; on unmount the value lingers without this clear).
  //    Skipped when a redirect is queued — clearing then would briefly
  //    null the conversation pane between the two states.
  $effect(() => {
    if ($page.url.searchParams.has('session')) return;
    if (sessions.selectedId !== null) {
      sessions.select(null);
    }
  });

  // 2. Legacy `?session=<id>` query-string deep-link. Handled here so
  //    an existing bookmark redirects without the user noticing. The
  //    redirect uses `replaceState: true` so the legacy URL doesn't
  //    pollute the browser history (back-button should land before the
  //    bookmark, not on it).
  $effect(() => {
    const legacyId = $page.url.searchParams.get('session');
    if (legacyId) {
      void goto(`/sessions/${encodeURIComponent(legacyId)}`, {
        replaceState: true,
      });
    }
  });

  // 3. Reload-preservation fallback. Only fires on a fresh entry
  //    (entered with no selection) — discriminated by the
  //    `enteredWithSelection` snapshot above so the explicit
  //    `/sessions/abc → /` navigation lands on the empty state and
  //    stays there. `attemptedInitialRedirect` is a one-shot guard
  //    against re-firing if the open list mutates (e.g. a WS upsert
  //    arrives) after the redirect attempt completes.
  //
  //    Effect waits for the sessions list to finish loading so we can
  //    verify the remembered id is still reachable in the open group
  //    before redirecting (a redirect to a deleted session would
  //    bounce the user right back to `/`).
  let attemptedInitialRedirect = $state(false);
  $effect(() => {
    if (attemptedInitialRedirect) return;
    if (enteredWithSelection) return; // user explicitly left a session
    if ($page.url.searchParams.has('session')) return; // path 2 owns this turn
    if (sessions.loading) return; // wait for the boot fetch
    if (sessions.list.length === 0) return; // empty database, nothing to restore
    attemptedInitialRedirect = true;
    const remembered = readRememberedId();
    if (!remembered) return;
    if (!sessions.openList.some((s) => s.id === remembered)) return;
    void goto(`/sessions/${encodeURIComponent(remembered)}`, {
      replaceState: true,
    });
  });
</script>

<!-- 3. Empty state. Rendered while the redirect effects decide what to
     do, and as the steady-state for users with no remembered session. -->
<section
  class="flex h-full items-center justify-center bg-slate-950 text-center"
  data-testid="root-empty-state"
>
  <div class="max-w-md px-6">
    <h1 class="text-base font-medium text-slate-200">Pick a session</h1>
    <p class="mt-2 text-sm text-slate-500">
      Choose a session from the sidebar, or start a new one with
      <kbd class="rounded bg-slate-800 px-1 text-xs text-slate-300">+ New</kbd>.
    </p>
  </div>
</section>
