<script lang="ts">
  /**
   * Tags page placeholder — Phase 2c of the v1.0.0 dashboard
   * redesign. The Tags nav item points here so the rail item is
   * functional from day one; the real tag-management UI (CRUD over
   * tag definitions, default-pinning, severity ordering) lands in a
   * follow-up phase. Today the sidebar's `TagFilterPanel` already
   * surfaces tag *filtering* — this future page is for tag *editing*,
   * which is currently scattered across right-click menus and the
   * SessionEdit modal.
   */
</script>

<section
  class="flex h-full flex-col items-center justify-center px-6 text-center"
  data-testid="placeholder-tags"
>
  <div class="rounded-md border border-slate-800 bg-slate-900 px-6 py-5">
    <h1 class="mb-2 text-base font-medium text-slate-200">Tags</h1>
    <p class="max-w-md text-sm text-slate-400">
      Tag management is coming in a follow-up phase. For now, tag filtering lives in the sidebar and
      tag editing happens via the right-click menu on a session row.
    </p>
  </div>
</section>
