import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  // es2022 so top-level await compiles cleanly (used by shiki WASM init in
  // src/lib/render.ts). All supported browsers already ship TLA.
  //
  // TEMP 2026-04-24: sourcemap enabled so the session-switch interrupt probe's
  // `_trace` field decodes to real component/line (e.g. Conversation.svelte:1550
  // vs ChecklistChat.svelte:108) instead of minified `2.BhvB7GyN.js:4:11511`.
  // Remove with the rest of the probe once the stop-frame origin is pinned down.
  build: { target: 'es2022', sourcemap: true },
  esbuild: { target: 'es2022' },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8787',
      '/ws': { target: 'ws://127.0.0.1:8787', ws: true }
    }
  }
});
