# Bearings v1 rebuild — deferred / orphaned work

Append the moment work is deferred or an error is passed on, per the
project CLAUDE.md "TODO.md Discipline" rule. Scheduled work belongs in
the master checklist (id `0f6e4006fb1d4340bda9983af3432064`), not here.

When a TODO is resolved, strike it from this file in the same commit
that lands the fix and cite the resolving commit hash in the removal
trailer.

## Resolved by item 3.3 (documentation pass)

* **Item 2.5 — chat.md augmentation for non-routing inspector
  subsections.** Resolved: `docs/behavior/chat.md` now carries an
  §"Inspector pane (non-routing subsections)" section describing the
  Agent / Context / Instructions tabs as shipped in commit `d0f5f68`.
  Cites arch §1.2 + the `SessionOut` wire shape per
  `src/bearings/web/models/sessions.py`.

## Deferred from item 2.1 (SvelteKit scaffolding + app shell)

The scaffold establishes empty directories under `frontend/src/lib/`
mirroring `docs/architecture-v1.md` §1.2. Each one tracks a future
item per the plan's build order. **Status:** all of the items below
landed during Phase 2 — kept here as a historical record of how the
scaffold ledger was discharged, not as outstanding work. Strike on the
next ledger sweep.

- `frontend/src/lib/themes/` — runtime theme provider, no-flash boot
  script, theme-color meta updater. **Item 2.9** wired the picker per
  `docs/behavior/themes.md` and tracks `data-theme` on `<html>`.
- `frontend/src/lib/keyboard/` — keybindings registry + cheat-sheet
  generator. **Item 2.9** registered every chord listed in
  `docs/behavior/keyboard-shortcuts.md` §"Bindings (v1)".
- `frontend/src/lib/context-menu/` — palette + registry + actions/.
  **Item 2.9** hooked the right-click handler per
  `docs/behavior/context-menus.md`.
- `frontend/src/lib/api/` — typed fetch clients per backend route
  group. Items 2.2-2.10 added files as their feature landed; 2.4 added
  `routing.ts` / `quota.ts` first.
- `frontend/src/lib/stores/` — Svelte 5 runes stores. Item 2.2 added
  `sessions.svelte.ts` + `tags.svelte.ts`; 2.3 added
  `conversation.svelte.ts`; 2.4-2.6 added routing / quota / usage
  stores per spec §6 + §10.
- `frontend/src/lib/components/{conversation,sidebar,inspector,settings,checklist,routing,vault,reorg,menus,icons,modals,feedback,common,pending}/`
  — populated by items 2.2-2.10 per arch §1.2 component groups.

## Item 2.1 — small inline-styling decision logged for 2.9 review

`+layout.svelte` carries a tiny `<style>` block containing the grid
geometry (`grid-template-columns: 16rem ... 20rem`). Tailwind has
arbitrary-value utility classes (`grid-cols-[16rem_minmax(0,_1fr)_20rem]`)
that could express the same thing — but the column widths are likely
to flex with theme density (item 2.9). **Item 2.9** should revisit:
either lift the geometry to `app.css` CSS variables (so the theme
picker can resize columns) or leave it scoped inline. No regression
risk; documenting so a future component author doesn't sprout a
parallel inline style for "theme-aware sizing."

## Item 2.9 — theme server-sync layer (deferred)

`docs/behavior/themes.md` §"Persistence boundary" prescribes
**per-account, server-synced** theme persistence with a "couldn't save
your theme" toast when the preferences PATCH fails. v1 ships
**localStorage-only** persistence: the runtime store reads / writes
``localStorage["bearings-theme-v1"]`` and listens to the browser-native
``storage`` event for cross-tab parity. Decision rationale:

- Bearings v1 is a single-user localhost app — "per account" degenerates
  to "the only account on this device", which is what localStorage
  already keys on.
- The arch §1.1.5 routes table lists ``web/routes/preferences.py``, but
  no preferences route, Pydantic models, or DB table exist yet. Adding
  schema + route + tests would expand this frontend item into a backend
  concern that a separate item should own (alongside other per-user
  preferences like the display timezone the doc mentions).
- The store interface is forward-compatible: a future item adds
  ``persistThemeToServer(theme)`` behind the same
  :func:`saveTheme` / :func:`loadTheme` shape used by the localStorage
  layer today, then re-points the toast copy at the network failure.

Action when the preferences route lands: extend
``frontend/src/lib/themes/persistence.ts`` to call the API client,
keeping localStorage as the synchronous boot-time read so the no-flash
guarantee holds.

## Item 2.1 — `{@html}` sanitization layer

Item 2.1 wires `marked` + `shiki` in `frontend/src/lib/render.ts` and
exercises it via `src/lib/__tests__/render.test.ts`, but does NOT use
`{@html}` at the SPA shell layer. **Item 2.3** owns the sanitization
contract for live conversation Markdown — when the renderer feeds
real user content into `{@html}`, that surface needs a DOMPurify (or
equivalent) sanitizer in line with chat.md's auto-link / file-path
linkifier rules. Don't ship the first `{@html}` of user content
without that layer.
