// Dynamic route — session ids are user-generated UUIDs that can't be
// enumerated at build time. adapter-static emits the SPA fallback
// (200.html, configured in svelte.config.js) for unmatched routes;
// FastAPI's _BundleStaticFiles serves it for any non-API path that
// doesn't resolve to a prerendered file. The client-side router then
// hydrates here and reads `params.id`.
//
// SSR is off because there's no useful server-rendered output for a
// session view that depends on the agent WebSocket and the live
// session store.
export const prerender = false;
export const ssr = false;
export const csr = true;
