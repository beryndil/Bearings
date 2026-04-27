import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      // SPA fallback for dynamic routes whose params can't be enumerated
      // at build time (e.g. /sessions/[id], where ids are user-generated
      // session UUIDs). adapter-static emits this file alongside the
      // prerendered routes; the FastAPI mount serves it for any unmatched
      // non-API path, then SvelteKit's client router takes over and the
      // page component reads `params.id` to drive store + agent state.
      //
      // Distinct filename (200.html) so it does NOT overwrite the
      // prerendered index.html. The prerendered index keeps its
      // route-specific CSS / modulepreload tags; 200.html carries the
      // generic SPA shell — the client router handles per-route asset
      // loading on first dynamic-navigation.
      fallback: '200.html',
      precompress: false,
      // `strict: true` requires every reachable route to be either
      // prerendered or covered by the fallback. With the fallback set,
      // dynamic routes with `prerender = false` qualify and the build
      // stays strict.
      strict: true
    })
  }
};

export default config;
