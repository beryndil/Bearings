import { defineConfig } from 'vitest/config';

// Kept separate from vite.config.ts so svelte-check's type-checking of
// the dev/build config doesn't pick up vitest-only fields. Pure-logic
// tests only for now — component tests would need jsdom +
// @testing-library/svelte and aren't worth the weight yet.
export default defineConfig({
  test: {
    include: ['src/**/*.{test,spec}.ts'],
    globals: false
  }
});
