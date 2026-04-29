/**
 * SvelteKit configuration for the Bearings v1 frontend.
 *
 * Static adapter — Bearings ships as a single-page app served by the
 * FastAPI backend (see `src/bearings/web/static.py`). The build artifact
 * lands at `../src/bearings/web/dist/` so it is included in the Python
 * wheel by `[tool.hatch.build.targets.wheel] packages = ["src/bearings"]`.
 *
 * `fallback: "index.html"` enables client-side routing: any path the
 * static server doesn't recognize falls back to the SPA shell, which
 * then renders the matching SvelteKit route.
 *
 * `vitePreprocess` runs the same TS/PostCSS pipeline as the rest of the
 * app, so `<script lang="ts">` and Tailwind directives in component
 * `<style>` blocks both work without ceremony.
 */
import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: "../src/bearings/web/dist",
      assets: "../src/bearings/web/dist",
      fallback: "index.html",
      precompress: false,
      strict: true,
    }),
    // Bearings is a single-user localhost app; no need for CSRF
    // origin checks beyond what FastAPI's middleware already enforces.
    // Inline a placeholder paths config so the build is reproducible
    // across `npm run build` and `npm run preview`.
    paths: {
      base: "",
    },
  },
};

export default config;
