<script lang="ts">
  /**
   * Analytics page placeholder — Phase 2c of the v1.0.0 dashboard
   * redesign. The Analytics nav item points here so the rail item is
   * functional from day one; the real Analytics dashboard (token
   * usage, cost trends, session counts) lands in Phase 6, backed by
   * the existing `/metrics` Prometheus surface plus per-session
   * aggregations from the SQLite store.
   */
</script>

<section
  class="flex h-full flex-col items-center justify-center px-6 text-center"
  data-testid="placeholder-analytics"
>
  <div class="rounded-md border border-slate-800 bg-slate-900 px-6 py-5">
    <h1 class="mb-2 text-base font-medium text-slate-200">Analytics</h1>
    <p class="max-w-md text-sm text-slate-400">
      Analytics ships in Phase 6 of the v1.0.0 dashboard redesign — token usage, cost trends, and
      session counts surfaced from <code class="rounded bg-slate-800 px-1 text-emerald-400"
        >/metrics</code
      > plus per-session aggregations from the SQLite store.
    </p>
  </div>
</section>
