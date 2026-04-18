<script lang="ts">
  import '../app.css';
</script>

<main class="grid h-full grid-cols-[280px_1fr_320px] gap-px bg-slate-800">
  <aside class="bg-slate-900 p-4 overflow-y-auto">
    <h2 class="text-sm uppercase tracking-wider text-slate-400">Sessions</h2>
    <p class="mt-4 text-slate-500 text-sm">No sessions yet.</p>
  </aside>

  <section class="bg-slate-900 p-4 overflow-y-auto flex flex-col">
    <header class="border-b border-slate-800 pb-3">
      <h1 class="text-lg font-medium">Twrminal</h1>
      <p class="text-xs text-slate-500">v0.1.0 scaffold — select or create a session to start.</p>
    </header>
    <div class="flex-1 mt-6 text-slate-500 text-sm">
      Conversation pane (placeholder).
    </div>
  </section>

  <aside class="bg-slate-900 p-4 overflow-y-auto">
    <h2 class="text-sm uppercase tracking-wider text-slate-400">Inspector</h2>
    <p class="mt-4 text-slate-500 text-sm">Tool calls, tokens, and diagnostics render here.</p>
  </aside>
</main>
