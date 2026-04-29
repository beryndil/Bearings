/**
 * Vite configuration for the SvelteKit frontend.
 *
 * Two execution contexts:
 *
 * 1. `npm run dev` — Vite serves on a dev port, proxying `/api/*` and
 *    `/ws/*` to the FastAPI backend (port 8788 per
 *    `src/bearings/config/constants.py:DEFAULT_PORT`). The dev server
 *    handles hot module reload; the backend handles data + streams.
 *
 * 2. `npm run build` — adapter-static produces a fully-prerendered SPA
 *    at `../src/bearings/web/dist/`. The FastAPI app serves the bundle
 *    via `bearings.web.static._BundleStaticFiles`.
 *
 * 3. `npm run test` — vitest runs in jsdom with @testing-library/svelte.
 *    `globals: true` so test files can use `expect`/`describe`/etc.
 *    without explicit imports (the standard vitest convention).
 */
import { sveltekit } from "@sveltejs/kit/vite";
import { svelteTesting } from "@testing-library/svelte/vite";
import { defineConfig } from "vitest/config";

const BACKEND_DEV_PORT = 8788;
const BACKEND_DEV_TARGET = `http://127.0.0.1:${BACKEND_DEV_PORT}`;

export default defineConfig({
  // `svelteTesting()` flips Svelte to the browser export condition so
  // vitest renders components against the client runtime — without it
  // `@testing-library/svelte` errors with `mount(...) is not available
  // on the server` per the Svelte 5 + vitest interop note.
  plugins: [sveltekit(), svelteTesting()],
  server: {
    proxy: {
      "/api": { target: BACKEND_DEV_TARGET, changeOrigin: false },
      "/ws": { target: BACKEND_DEV_TARGET, ws: true, changeOrigin: false },
      "/openapi.json": { target: BACKEND_DEV_TARGET, changeOrigin: false },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    include: ["src/**/*.{test,spec}.{ts,svelte.ts}", "tests/**/*.{test,spec}.ts"],
    setupFiles: ["./vitest.setup.ts"],
  },
});
