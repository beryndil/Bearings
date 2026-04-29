<script lang="ts">
  /**
   * Default landing route — renders inside the app shell's center column
   * (`+layout.svelte` →  `<section class="app-shell__main-body">`).
   *
   * Item 2.2's sidebar will render an actual session list; clicking a
   * session navigates to `/sessions/<id>`, which in turn renders that
   * session's conversation in this same slot. Until then, the landing
   * page is the empty-state placeholder.
   *
   * The `marked` + `shiki` wiring item 2.1 ships lives in
   * `$lib/render` and is exercised by `src/lib/__tests__/render.test.ts`;
   * item 2.3 (Conversation + streaming) hooks the renderer into live
   * message bubbles with the appropriate sanitization layer (the SPA's
   * `{@html}` surface is gated to user-content paths there, not here).
   */
</script>

<div class="flex h-full flex-col items-center justify-center gap-2 text-center">
  <h2 class="text-lg font-medium text-fg-strong">No session open</h2>
  <p class="max-w-md text-sm text-fg-muted">
    Pick a session from the sidebar, or start a new one with <kbd
      class="rounded border border-border bg-surface-2 px-1 font-mono text-xs">c</kbd
    >. The full session list lands in item 2.2.
  </p>
</div>
