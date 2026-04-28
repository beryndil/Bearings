# Bearings frontend (skeleton)

This directory holds tool configuration only. The actual SvelteKit app
(routes, components, build) lands in **item 2.1 — SvelteKit scaffolding +
app shell** per `~/.claude/plans/bearings-v1-rebuild.md`.

What's here at item 0.1:

* `package.json` — dev-dep manifest declaring all 6 frontend tools required
  by the tooling matrix (eslint, prettier, svelte-check, knip, ts-prune,
  depcheck).
* `tsconfig.json`, `eslint.config.js`, `.prettierrc.json`, `knip.json`,
  `.depcheckrc.json` — config files so item 2.1 starts with a wired
  toolchain and only adds sources.
* `src/` — empty directory; svelte/TS sources arrive in 2.1.

What's deliberately NOT here at item 0.1:

* `node_modules/` — `npm install` is item 2.1's responsibility; CI for
  item 0.1 does not install Node deps.
* SvelteKit config / Vite config / app.html — those are 2.1.

The pre-commit hooks for the 6 frontend tools are gated on
`files: ^frontend/.*\.(ts|svelte|json|js)$` so they no-op cleanly on
backend-only commits and on this scaffolding commit.
