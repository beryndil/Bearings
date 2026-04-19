import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

// Kept separate from vite.config.ts so svelte-check's type-checking of
// the dev/build config doesn't pick up vitest-only fields. Runs under
// jsdom so component tests can mount into a document; pure-logic tests
// don't notice the environment.
export default defineConfig({
  plugins: [svelte({ hot: false })],
  // `resolve.conditions` / `server.deps.inline` so Svelte 5 picks the
  // client entry (index-client.js) under jsdom instead of its
  // SSR-only `index-server.js` — otherwise mounting real components
  // throws.
  resolve: {
    conditions: ['browser']
  },
  test: {
    include: ['src/**/*.{test,spec}.ts'],
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./vitest.setup.ts'],
    server: {
      deps: {
        inline: [/^svelte/]
      }
    }
  }
});
