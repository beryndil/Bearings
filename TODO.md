# Bearings v1 rebuild — deferred / orphaned work

Append the moment work is deferred or an error is passed on, per the
project CLAUDE.md "TODO.md Discipline" rule. Scheduled work belongs in
the master checklist (id `0f6e4006fb1d4340bda9983af3432064`), not here.

When a TODO is resolved, strike it from this file in the same commit
that lands the fix and cite the resolving commit hash in the removal
trailer.

~~## load_schema executescript ordering bug — legacy DB server restart failure (2026-05-09)~~

~~`load_schema` calls `executescript(schema_sql)` before `_ensure_added_columns`.
On a live DB that predates `pivot_message_id` (and other _ADDED_COLUMNS entries),
`schema.sql`'s `CREATE INDEX idx_sessions_pivot_message_id ON sessions(pivot_message_id)`
fails with `no such column: pivot_message_id` because the column hasn't been
ALTERed in yet. Workaround during F1-RT-00 restart: manually applied all missing
_ADDED_COLUMNS via sqlite3 CLI to unblock startup. Real fix: move
`_POST_ALTER_INDEXES` entries out of `schema.sql` (leave them only in
`connection.py`), OR gate the index creation inside `_ensure_added_columns` only.
Not blocking Phase 2 — server is now running. Schedule as a maintenance item.~~

~~Resolved by commit `742a01d0` (fix(db): move post-alter indexes out of schema.sql to fix restart bug).
`idx_sessions_pivot_message_id` removed from schema.sql; already present in
`_POST_ALTER_INDEXES` in connection.py. Three tests added:
`test_pivot_message_id_index_exists_on_fresh_boot`,
`test_pivot_message_id_upgrade_on_legacy_db`,
`test_pivot_message_id_reinit_is_idempotent`.~~

~~## knip gate failure — pre-existing unused frontend exports (2026-05-08)~~

~~`uv run pre-commit run --all-files` exits 1 because the knip hook finds 1
unused file (`frontend/src/lib/components/common/DataViewHarness.svelte`),
4 unused exports (including `EXECUTOR_MODEL_OPUSPLAN`, `_resetForTests`,
`BOOT_STORAGE_KEY`, `_resetBillingModeCacheForTests`), and 27 unused
exported types (API interfaces in `src/lib/api/*.ts` and store/utility
types). These findings predate feature-12 work and are not a feature-12
regression. The feature-12-003 executor's verification was incomplete —
it claimed knip passes when it does not. Surfaced by feature-12 closer
session `d3a0fc02a9e64f359aeb7bc5cfb4e18f`. Resolve by: (a) removing
or internalising `DataViewHarness.svelte`, (b) deciding per export
whether to delete, narrow export scope, or add a `// knip:ignore`
comment, and (c) for API types consumed only by tests, either move them
to test helpers or add `@internal` annotations per the knip config.~~

~~Resolved by commit `0e59f0a8` (fix(quality-gates): pytest smoke, xenon CC, knip). All unused exports removed; knip exits 0 cleanly.~~

## v1.1 closing-sweep (2026-05-02) — corrects v1.0's lying close

The 2026-04-29 close of the v1 master checklist
(`0f6e4006fb1d4340bda9983af3432064`) marked 29/29 items DONE without
artifact verification. The 2026-05-02 audit
(`bearings__get_tool_output toolu_01LjpFH7TnMzpGR81Z325Ky3`) found
~25% of arch §1.1.5 unbuilt — including the entire session-create
flow (button → broken route, no `POST /api/sessions`, NewSessionForm
orphaned). The v1.1 closing-sweep
(`~/.claude/plans/belated-closing-sweep.md`) closes the gap.

What v1.1 ships:

* **Phase 0.** ``POST /api/sessions`` + ``/sessions/new`` route +
  NewSessionForm submit wiring.
* **Phase 1.** RoutingRuleEditor mounted in ``/settings`` (system) +
  ``/tags`` (per-tag); ``/tags`` and ``/analytics`` stub pages
  replaced with real management surfaces; ChecklistChat orphan deleted.
* **Phase 2.** ``PATCH /api/sessions/{id}/model`` (full live swap —
  persists the new model AND recycles the SDK supervisor so the next
  prompt respawns with ``--model <new>``) +
  ``POST /api/sessions/{id}/regenerate``.

What v1.1 defers (logged below):

* ~~PairedChatIndicator wiring.~~ (resolved: component mounted in 33b3a55c)
* The 12 spec'd route modules from arch §1.1.5 — all absent in v1.0
  AND with zero v1 frontend consumers; deferred per the plan's
  "KEEP only modules with a v1 frontend consumer" rule.
* `bearings serve` CLI (entry below predates this sweep).
* `/api/usage/headroom` rename (entry below predates this sweep).
* Theme server-sync (entry below predates this sweep).

## Resolved by item 3.4 (final ledger sweep)

The ledger entries below were swept on the cutover-smoke commit (item
3.4, master id `0f6e4006fb1d4340bda9983af3432064` final entry).

* **Item 2.5 — chat.md augmentation for non-routing inspector
  subsections.** Resolved by item 3.3 documentation pass (commit
  `8e9bcd7`); chat.md §"Inspector pane (non-routing subsections)"
  describes Agent / Context / Instructions tabs.
* **Item 2.1 — SvelteKit scaffolding ledger (themes / keyboard /
  context-menu / api / stores / components).** Every directory the
  scaffold reserved was populated by items 2.2 – 2.10 in the Phase 2
  build order; no scaffold dirs remain empty.
* **Item 2.1 — inline-styling decision logged for 2.9 review.**
  Resolved by item 2.9 (commit `5e936e4`): the grid geometry stays
  scoped inline in `+layout.svelte`. The theme picker's density
  surface does not resize columns, so the CSS-variable hoist was not
  warranted. Documented here so a future component author defaults to
  the same choice if they sprout a similar inline style.
* **Item 2.1 — `{@html}` sanitization layer.** Resolved by item 2.3
  (commit `33b3a55`): `frontend/src/lib/sanitize.ts` wraps
  `isomorphic-dompurify` with the Bearings policy; `MessageTurn.svelte`
  routes every conversation `{@html}` through `sanitizeHtml()` before
  insertion. `linkifyToHtml()` output is also re-sanitized at the
  bubble seam for defense in depth.

## Item 3.4 — fix landed during the cutover smoke

* **Migration title-coercion.** v0.17 admitted NULL titles, empty-
  string titles, and titles longer than v1's 500-char dataclass
  invariant. The cutover smoke surfaced a 500 on `GET /api/sessions`
  the first time it ran against the live `~/.local/share/bearings/db.sqlite`
  (one outlier title was 1504 chars). The migration script now coerces
  NULL / empty titles to a `(untitled)` sentinel and truncates over-
  cap titles with an ellipsis suffix. Tests
  `tests/test_migrate_v0_17_to_v0_18.py::test_null_title_backfills_to_sentinel`,
  `::test_empty_title_backfills_to_sentinel`, and
  `::test_long_title_truncated` cover the three branches.

## Open follow-ups from the 2026-05-03 stuck-session diagnosis

A live session (`ses_8f8aa4d947df670b2cc57d0dfacb2bb1`) ran into the
SDK control-request init timeout, after which every subsequent prompt
POST silently queued without a reply. Fix landed in this commit:
`web/runner_factory.py` now treats `task.done()` as 'supervisor gone'
so reap-recovery actually fires after a fatal SDK error, and
`agent/sdk_loop._enter_error_state` logs the traceback to journald
so future failures are operator-visible. Two pieces remain.

### Root cause of the original initialize timeout — unknown

The SDK's `_send_control_request("initialize")` timed out at 60s once
in a long-running bearings python process. Direct out-of-process
probes with the same bearings options (in-process MCP server,
`bypassPermissions`, full `compose_session_options` output) spawn the
`claude` CLI and complete `initialize` in <2s. So whatever made the
live process hang was **process-state-dependent**, not a config or
SDK-version issue. Plausible angles before the next occurrence:

* Long-running python with many WS subscribers — investigate whether
  fd / stdio inheritance into the spawned CLI is sensitive to parent
  state.
* Concurrent supervisor spawn lock — check whether two near-simultaneous
  POSTs across distinct sessions can lock `_send_control_request`.
* SDK ↔ `claude` CLI version skew (pin `~=0.1.69` vs CLI 2.1.126) —
  pin the CLI version somewhere reproducible (npm shrinkwrap or
  documented version floor).

When this recurs, the new `_log.warning` in `sdk_loop` will surface
the traceback in journald — capture it before doing anything else.

**Status check 2026-06-02**: no root-cause fix commits found. Entry remains open.

~~### `POST /api/sessions/{id}/recover` HTTP route — missing~~

~~Resolved by commit `cc4ea35` (Phase 4 of the UI/UX gap sweep). Route
`POST /api/sessions/{id}/recover` (handler `resume_session`) added to
`web/routes/sessions.py`; DB `set_error_pending()` added; frontend
Recover button wired in `Conversation.svelte`; `is_error` field added
to `RunnerStatus` + `runner_state` WS frame + sessions store handler
so the sidebar pip lights immediately on error without a page reload.~~

## Remaining deferrals (post-v1 scope)

> **Tracked in checklist session `ses_5301b9896456b66c41ce5a87dbd49054`**
> ("Bearings v1.1 — Deferred work"). All five named items below plus
> the 12 per-module route stubs have been migrated to that checklist.
> Edit this file when an item resolves; strike it here and cite the
> commit hash per TODO.md discipline.

~~### Theme picker silently flips to OS scheme on first paint — 2026-05-02~~

~~Resolved by commit `c730cba` (Phase 6 of the UI/UX gap sweep).
`resolveBootTheme()` now persists the OS-fallback choice to localStorage
on first boot so subsequent loads skip the OS check and the static
`data-theme="evergreen"` in `app.html` stays consistent across reloads.~~

**Action**: either (a) drop the OS fallback so the static-HTML default
(`evergreen`) is the sole "no persisted choice" path, or (b) make the
picker write the OS-fallback resolution into localStorage on first
boot so the choice surfaces in the UI. Probably (b) — keeps OS-aware
defaulting, removes the silent flip.

### Daily-probe `/api/usage/headroom` endpoint swap — 2026-05-01

Master item B.1 (daily probe script) names `/api/usage/headroom` in
its done-when criteria. That endpoint does not exist in v1's route
surface (verified against the live `/openapi.json` — only
`/api/usage/by_model`, `/api/usage/by_tag`, `/api/usage/override_rates`
are present). The probe instead hits `/api/quota/current` +
`/api/quota/history` to cover the headroom-conceptual surface (the
inspector's 7-day headroom chart already reads from those).

**Action when a literal `headroom` endpoint lands** (if ever — the
data surface is fully covered by `quota/*` today, so this may be a
permanent rename rather than a missing route): swap the
`quota_current` / `quota_history` rows in `scripts/daily_probe.py`
`PROBES` for one `headroom` row pointing at the new path, drop this
TODO entry, cite the resolving commit.



### Item 2.9 — theme server-sync layer (deferred)

`docs/behavior/themes.md` §"Persistence boundary" prescribes
**per-account, server-synced** theme persistence with a "couldn't save
your theme" toast when the preferences PATCH fails. v1 ships
**localStorage-only** persistence: the runtime store reads / writes
``localStorage["bearings-theme-v1"]`` and listens to the browser-native
``storage`` event for cross-tab parity. Decision rationale:

- Bearings v1 is a single-user localhost app — "per account" degenerates
  to "the only account on this device", which is what localStorage
  already keys on.
- ~~The arch §1.1.5 routes table lists ``web/routes/preferences.py``, but
  no preferences route, Pydantic models, or DB table exist yet.~~ **Update
  2026-06-02**: `preferences.py` now exists. Review whether the route surface
  is sufficient for theme server-sync, or if DB/model work remains.
- The store interface is forward-compatible: a future item adds
  ``persistThemeToServer(theme)`` behind the same
  :func:`saveTheme` / :func:`loadTheme` shape used by the localStorage
  layer today, then re-points the toast copy at the network failure.

**Action when the preferences route lands** (post-v1 work item to be
scheduled separately): extend
``frontend/src/lib/themes/persistence.ts`` to call the API client,
keeping localStorage as the synchronous boot-time read so the no-flash
guarantee holds.

### Closing-sweep gap log — 2026-05-02

The 2026-05-02 audit (`bearings__get_tool_output`
`toolu_01LjpFH7TnMzpGR81Z325Ky3`) found ~25% of arch §1.1.5 unbuilt
despite the v1 master checklist
(`0f6e4006fb1d4340bda9983af3432064`) marking 29/29 DONE. The
closing-sweep plan (`~/.claude/plans/belated-closing-sweep.md`) is
the source of truth for the work; the entries below are deferrals
that arose during execution.

#### ~~PairedChatIndicator wiring (deferred)~~

~~Stale entry — `PairedChatIndicator.svelte` is imported and mounted in
`ConversationHeader.svelte`. Entry removed per feature-6-009 closeout;
resolving commit `33b3a55c`.~~

#### Missing arch §1.1.5 route modules (deferred — no v1 UI consumer)

The audit flagged 12 spec'd route modules absent from
``src/bearings/web/routes/``:

* ~~``sessions_bulk.py`` — bulk close/reopen/delete/tag.~~ (resolved: gap-cycle-13-001)
* ~~``checkpoints.py`` — chat-undo checkpoint CRUD.~~ (resolved: module exists 2026-06-02)
* ~~``templates.py`` — Templates CRUD.~~ (resolved: module exists 2026-06-02)
* ~~``reorg.py`` — session-reorg analyze + apply.~~ (resolved: module exists 2026-06-02)
* ~~``spawn_from_reply.py`` — ``+ SPAWN`` action on a reply.~~ (resolved: gap-cycle-03-007)
* ``reply_actions.py`` — inline reply-action execution.
* ``artifacts.py`` — artifact register + serve.
* ~~``commands.py`` — slash-command palette scan.~~ (resolved: module exists 2026-06-02)
* ~~``preferences.py`` — per-user preferences.~~ (resolved: module exists 2026-06-02)
* ~~``pending.py`` — ``.bearings/pending.toml`` ops.~~ (resolved: module exists 2026-06-02)
* ~~``history.py`` — ``history.jsonl`` reader.~~ (resolved: module exists 2026-06-02)
* ``config.py`` — ``/api/ui-config`` runtime knob exposure.

Per-commit grep over ``frontend/src/**/*.{ts,svelte}`` (excluding
test files) found **zero** consumers for any of these endpoints in
v1.1's frontend tree. Building backend modules with no frontend
caller is dead-weight code; deferring per the closing-sweep plan's
"KEEP only modules with v1 frontend consumers" decision.

The audit's claim that ``/api/checklists`` list+create is absent
turned out to be a non-issue: checklists are sessions of
``kind="checklist"``, so the unified ``/api/sessions`` list+create
landed in this sweep covers them. The audit's claim about a
session-level bulk-tag-set endpoint (``PUT /api/sessions/{id}/tags``)
is similarly unbacked — the existing per-tag attach/detach
endpoints are what the v1 frontend uses.

**Action when each module's UI consumer lands**: implement the
backend module from arch §1.1.5 in the same commit that lands the
frontend caller. The arch doc is the source of truth for the route
shape; the per-module test patterns in
``tests/test_*_api.py`` are the reference for the integration tests.

#### ~~ChecklistChat — deleted (no documented role)~~

~~Stale entry — `ChecklistChat.svelte` exists and is mounted in
`ChecklistView.svelte`. Re-added with behavior doc in commit `404c1818`
(gap-cycle-01-014). Entry removed per feature-6-009 closeout;
resolving commit `404c1818`.~~

## Pre-existing frontend build failure (surfaced 2026-06-03)

`npm run build` fails with:
```
[MISSING_EXPORT] "getWorkEvidence" is not exported by "src/lib/api/sessions.ts"
```
Caused by `frontend/src/lib/components/inspector/InspectorAgent.svelte`
importing `getWorkEvidence` and `WorkEvidenceOut` from `../../api/sessions`.
Neither export exists. Fix: either add the export to `api/sessions.ts` or
remove the import from `InspectorAgent.svelte` if the feature is deferred.

Also pre-existing: `CheckpointGutter.svelte` has two unused imports
(`compareCheckpoint`, `CheckpointCompareResult`) that cause svelte-check errors.

## Pre-existing test failures (surfaced 2026-06-03)

Four tests were already failing before the 4-8 model-update commit:

- `test_broadcaster_ccw3.py::test_mutation_routes_have_publish_calls` —
  `suggest_session_title (POST)` route is missing a `publish_*` call.
  Fix: add a broadcaster publish call to the suggest-title handler in
  `src/bearings/web/routes/sessions.py`.

- `test_operation_ids.py::test_operation_id_count` — expected 148
  operations, actual is 152. Four routes were added after the test
  was last updated. Fix: update the count comment + assertion in
  `tests/test_operation_ids.py` to 152 and document which 4 routes
  were added.

- `test_diff_probe.py::test_run_probe_diverge_path` — assertion failure
  in the end-to-end diverge-path probe test. Independent of model versions.
  Likely a test scaffolding issue post-refactor.

- `test_consistency_lint.py::test_live_repo_is_clean` and
  `test_main_returns_zero_on_clean_repo` — these pass on a clean working
  tree and fail with uncommitted changes; they will auto-pass after the
  next commit.

**Status check 2026-06-03**: all four confirmed pre-existing.

## Push backlog — SSH proxy config permissions (2026-05-04)

`git push` from the tag-class feature work (commit `a911687` and
follow-up commits, including the 2026-05-05 SDK history-replay fix at
`e641892`) failed with `Bad owner or permissions on
/etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf`. The directory
`/etc/ssh/ssh_config.d/` is owned by `nobody:nobody` (regression from
a recent `systemd` update — the symlink target lives at
`/usr/lib/systemd/ssh_config.d/`). Local commits landed on
`v1-rebuild` but did not propagate to `origin/v1-rebuild`. Fix with:

    sudo chown root:root /etc/ssh/ssh_config.d /etc/ssh/ssh_config.d/*

Then `git push` to drain the backlog. Resolve in the same commit that
sweeps the fix. The agent worktree runs with `--no-new-privileges`, so
the chown must be issued from a regular shell.

**Status check 2026-06-02**: still blocked. Push fails with same SSH proxy error.

~~## CLAUDE.md stale v17 path (2026-05-06)~~

~~Project `CLAUDE.md` and the "Reference-read protocol" section refer to
`/home/beryndil/Projects/Bearings/` as the v0.17.x reference tree.
That path no longer exists — v0.17.x was relocated to
`/home/beryndil/Projects/archive/bearings-v0.17.x/`. The autonomous
parity loop driven from `~/.claude/plans/melodic-toasting-axolotl.md`
uses the archive path in its auditor instructions. Update the project
`CLAUDE.md` "Authoritative documents" / "Reference-read protocol"
references to the archive path in the next chore commit.~~

~~Resolved by chore commit (chore: strike resolved TODO entries (knip, svelte-check, CLAUDE.md path)). CLAUDE.md updated to reference `/home/beryndil/Projects/archive/bearings-v0.17.x/`.~~

~~## API gap: no PATCH for session description (2026-05-05)~~

~~`PATCH /api/sessions/{id}` accepts only `SessionTitleUpdate` (title
field). Other per-attribute PATCHes exist for `model`,
`permission_mode`, `pinned`, etc. — but `description` has no update
endpoint, even though `SessionOut` and `SessionCreate` carry the field.
Blocks the dual-persist contract in `~/.claude/skills/persisting-plans`
(plug-update half is a no-op on this Bearings). Add either
`PATCH /api/sessions/{id}/description` or extend `SessionTitleUpdate`
into `SessionMetadataUpdate` accepting both fields. Surfaced while
authoring `~/.claude/plans/resolute-restructuring-projects.md` from
session `ses_3794490d13075208149c2903fed6b8c0`.~~

~~Resolved: `SessionUpdate` model already supported description patching
via `PATCH /api/sessions/{id}`. Tests added confirming functionality.
Item A1 of Orch-A sweep, 2026-06-02.~~

~~## feature-12-001: pre-existing cyclomatic complexity violations (2026-05-07)~~

~~Xenon now enforces the CC ≤ 10 coding standard (replaces cosmetic radon gate).
The enforcing gate immediately surfaces pre-existing violations the old gate
never caught. Running `uv run xenon --max-absolute B --max-modules A
--max-average A src` exits 1 with ~40 C/D-ranked blocks across:~~

~~- `src/bearings/web/routes/sessions.py` (7 blocks, incl. rank D)~~
~~- `src/bearings/db/sessions.py` (3 blocks, 2 rank D)~~
~~- `src/bearings/agent/session_assembly.py` (1 block, rank D)~~
~~- `src/bearings/web/routes/templates.py` (2 blocks, 1 rank D)~~
~~- `src/bearings/db/` (several C-rank blocks in messages, routing, tags, etc.)~~
~~- `src/bearings/agent/` (sdk_loop, routing, sentinel, paired_chats, quota)~~
~~- `src/bearings/cli/` (todo, gc)~~

~~**Action**: schedule a complexity-reduction sprint to refactor these blocks
below CC 10. Until then, `pre-commit run --all-files` and the CI `xenon`
step will fail on unchanged code. The gate configuration is correct; the
codebase is the non-compliant party.~~

~~Resolved by commit `0e59f0a8` (fix(quality-gates): pytest smoke, xenon CC, knip). xenon exits 0 cleanly.~~

~~## gap-cycle-13-004: template_baseline layer deferred~~

~~`GET /api/sessions/{id}/system_prompt` defines `template_baseline` as a layer kind
but never emits it. Template `system_prompt_baseline` is baked into
`session_instructions` at session-creation time and there is no `template_id` FK
on the session row to recover the original text. Emit `template_baseline` when
sessions gain a `template_id` column.~~

~~Resolved by item 622 (`feat(db,api): template_id FK + template_baseline layer`):
`sessions.template_id` FK added (schema.sql + `_ADDED_COLUMNS` ALTER for legacy
DBs), set by `POST /api/templates/{id}/instantiate`, and the assembler now emits
the `template_baseline` layer when it is non-null.~~

~~## feature-13-010 deferred: x-sunset extension + Sunset header middleware~~

~~Deprecation convention (docs/deprecation-convention.md) is established.
The two remaining parts are deferred to v1.1.0:~~

~~1. **`x-sunset` extension** — add `openapi_extra={"x-sunset": "v1.2.0"}` to
   `GET /api/tag-groups` (tags.py) and the `tag_ids` param route decorator
   (sessions.py). Regen openapi.json in the same commit.~~

~~2. **Sunset response header middleware** — author
   `src/bearings/web/middleware/sunset.py`: ASGI middleware that emits
   `Sunset: <date>` for requests whose matched route carries `x-sunset` in
   `openapi_extra`. Wire into `create_app()`. Add unit test asserting header
   present on `GET /api/tag-groups`, absent on non-deprecated routes.~~

~~Must land before any deprecated surface is removed (earliest: v1.2.0).~~

~~Resolved: `openapi_extra={"x-sunset": "v1.2.0"}` added to `GET /api/tag-groups`.
`SunsetMiddleware` in `src/bearings/web/middleware/sunset.py` emits `Sunset`
header for routes with `x-sunset`. Tests in `tests/test_middleware_sunset.py`.
Item A2 of Orch-A sweep, 2026-06-02.~~

~~## svelte-check: 9 pre-existing type errors (2026-06-02)~~

~~`npm run check` exits non-zero with 9 errors across 3 files. These predate
the quality-gate sweep in this commit and are not regressions from it.~~

~~**`frontend/src/lib/stores/sessions.svelte.ts`** (3 errors):~~
~~- Line 31: `SessionTagOut` imported but never read.~~
~~- Lines 311, 359: `params` is possibly `undefined`.~~

~~**`frontend/src/lib/components/menus/SessionPickerModal.svelte`** (3 errors):~~
~~- Line 62: `Property 'filter' does not exist on type 'SessionsPage'` — component
  calls `.filter()` directly on the paginated API envelope instead of on
  `.sessions`. Fix: unwrap `store.sessions` before filtering.~~

~~**`frontend/src/lib/components/reorg/ReorgPicker.svelte`** (4 errors):~~
~~- Lines 116–117: same `SessionsPage.find/filter` issue as above.~~

~~Fix: update the two Svelte components to read `.sessions` from the store
value before calling array methods; remove the unused `SessionTagOut` import.~~

~~Resolved by commit `c1b2177c` (fix(frontend): resolve 9 pre-existing svelte-check type errors).~~
