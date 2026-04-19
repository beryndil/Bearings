import { svelte } from '@sveltejs/vite-plugin-svelte';
import path from 'node:path';
import { defineConfig } from 'vitest/config';

// Kept separate from vite.config.ts so svelte-check's type-checking of
// the dev/build config doesn't pick up vitest-only fields. Runs under
// jsdom so component tests can mount into a document; pure-logic tests
// don't notice the environment.
export default defineConfig({
  plugins: [svelte({ hot: false })],
  resolve: {
    // Svelte 5 ships both server and client entries. Without the
    // `browser` condition, jsdom pulls index-server.js and mount
    // throws.
    conditions: ['browser'],
    // SvelteKit injects the `$lib` alias at build time; for vitest
    // we resolve it manually so component imports work.
    alias: {
      $lib: path.resolve(__dirname, 'src/lib')
    }
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
