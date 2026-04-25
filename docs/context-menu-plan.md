# Context Menu System — Implementation Plan

**Target release train:** v0.9.0-alpha → v0.9.3
**Baseline:** v0.8.0
**Spec authority:** canonical context-menu spec (registry-driven, 17 target
types, ~150+ actions). This document plans implementation; it does not
restate the spec.

Status: **planning — phases 1-13 implemented in v0.9.x; phases 14-16
unblocked 2026-04-25** by §8.3/§8.4/§8.5 resolutions. Five governing
decisions made (§2). Three open questions remain (§8: Chrome flag,
touch long-press tests, slash-command collision).

---

## 1. Context

The frontend has zero `contextmenu` listeners today. Right-click is 100%
native Chrome behavior. The spec introduces a registry-driven context-menu
system with custom UI for every significant surface (session rows, tag
chips, message bubbles, code blocks, tool calls, file edits, checkpoints,
search results, etc.) plus a Ctrl+Shift+P command palette that enumerates
every registered action across every target type.

The backend already services ~70% of the actions the spec wants to expose
(session/tag/message CRUD, reorg, export, tag memories, history search,
config, fs listing, commands listing). Gaps cluster in: checkpoints
(new DB primitive), message flags (pin / hide-from-context), shell-open
bridge (editor / terminal / git GUI / Claude CLI), templates, bulk ops,
attachments.

`Conversation.svelte` is 1424 lines — 3.5× the 400-line cap. It is
immovable as-is. This plan treats it as a directive-only surface: attach
`use:contextmenu` attributes, push all handler logic to
`actions/<target>.ts` files. No new handler bodies may land in
`Conversation.svelte`.

---

## 2. Governing decisions

### 2.1 "Change model for continuation" mutates in place

The action patches the session's `model` column for subsequent turns. Past
turns retain their original model attribution. Cost rows already track
per-turn, so mixed-model history is not a new problem.

Rationale: the label says "for continuation" — forward-looking. The
session menu already has **Duplicate** (fresh session, same context) and
**Fork from last message** for the "I want a new sidebar row" case.
Making "change model" also fork duplicates those.

Backend: `PATCH /sessions/{id}` accepts `{ model }`; agent registry
invalidates the cached SDK subprocess; next user turn boots fresh.
No migration.

### 2.2 Archive is an alias for Close

The `session.archive` action ID maps to the existing
`POST /sessions/{id}/close` route. No new column. No new state. No
History panel. The existing "Closed" sidebar group is already
collapsed-by-default — that is the archive behavior.

Rationale: two-state hidden/closed systems always confuse users a quarter
later. If deeper hiding is needed, tag filters already provide it, and
they are more flexible than a boolean. The rename direction (alias
archive → close) is friendly to a future split: the action ID stays
stable if we later decide to grow a distinct archived state.

Implication: planned migration 0022 **drops** the `archived_at` column and
keeps only `sessions.pinned`.

### 2.3 Hybrid stub vs disabled-with-tooltip

The spec's build-order step 3 says "stubbed with 'Not yet implemented'
toasts for unbuilt features." Amend to split:

- **Route exists, returns 501** → stub toast on click. Honest: "this
  button does its job; the backend doesn't yet."
- **Underlying DB primitive / table does not exist yet** (checkpoint,
  template, attachment) → action renders **disabled with tooltip**
  naming the target milestone ("Checkpoints land in v0.9.2"). Never
  clickable.

Rationale: a stub toast is dishonest when the feature cannot possibly
work — the user cannot tell whether they made a mistake or the feature
is absent. Disabled-with-tooltip signals *coming soon* without
pretending it's there. The registry's `disabled: (target) => string |
null` predicate already supports this — no new mechanism.

### 2.4 Ctrl+Shift+P command palette ships in Phase 4, not Phase 12

The spec references Ctrl+Shift+P for discoverability. The exploratory
plan deferred it to Phase 12 (polish). Move it forward to Phase 4,
alongside the first real session/tag menus.

Rationale: discoverability is day-one. A context-menu-only launch where
users must right-click every possible surface to discover features is
hostile. The palette reuses the registry built in Phase 1 — marginal
cost is ~1 Svelte component that cribs heavily from the existing
`CommandMenu.svelte` (slash command) and `SessionPickerModal.svelte`
(filter + keyboard) patterns. Phase 4 is when the registry fills with
real actions; earlier ships an empty palette, later arrives as an
apology.

Phase 12 in the exploratory plan dissolves. Phase 13 (Ctrl+? help mode)
stays late — that is genuine polish.

### 2.5 Shift-right-click = advanced; Ctrl+Shift+right-click = native

Spec wins: Shift-right-click opens our menu in advanced mode
(items marked `advanced: true` become visible). The native-menu escape
hatch chord becomes **Ctrl+Shift+right-click**. Both documented in
`CheatSheet.svelte`.

Rationale: the Chrome convention of "shift-right-click forces native"
is niche; most users who want DevTools use F12, and who want View
Source use Ctrl+U. The common case (power users surfacing advanced
actions) gets the simpler chord; the rare case (dev escape hatch)
gets the modified chord. One three-line branch in the `contextmenu`
listener handles both.

Listener logic:

```
if (e.ctrlKey && e.shiftKey) return;          // native menu passthrough
const advanced = e.shiftKey;                  // advanced mode on
e.preventDefault();
openContextMenu({ target, x, y, advanced });
```

---

## 3. Module layout

All new files respect the 400-line cap. Paths absolute from repo root.

### 3.1 Frontend — new files

```
frontend/src/lib/components/context-menu/
├── ContextMenu.svelte              ≤ 300  Generic renderer
├── ContextMenuItem.svelte          ≤ 120  Row + submenu expander
├── ContextMenuSubmenu.svelte       ≤ 150  Submenu container
├── ConfirmDialog.svelte            ≤ 200  Destructive confirm modal
├── UndoToastHost.svelte            ≤ 150  Stack of reversible-action toasts
├── StubToast.svelte                ≤ 80   "Not yet implemented" toast
└── CommandPalette.svelte           ≤ 250  Ctrl+Shift+P global action finder

frontend/src/lib/context-menu/
├── types.ts                        ≤ 200  Action / Section / TargetType
├── registry.ts                     ≤ 250  Default+TOML merge, lookup, aliases
├── positioning.ts                  ≤ 250  Viewport + submenu flip math (pure)
├── keyboard.ts                     ≤ 200  Arrow/Enter/Esc/mnemonic FSM (pure)
├── shortcuts.ts                    ≤ 200  Global shortcut registry
├── toml-loader.ts                  ≤ 250  Parse + validate menus.toml payload
├── confirm.svelte.ts               ≤ 150  $state for dont-ask-again set
├── undo.svelte.ts                  ≤ 120  Queue store for undo toasts
├── stub.svelte.ts                  ≤ 80   Stub-toast store
├── touch.ts                        ≤ 150  Long-press + pointer-coarse
└── actions/
    ├── session.ts                  ≤ 400
    ├── tag.ts                      ≤ 300  tag + tag_chip
    ├── message.ts                  ≤ 350
    ├── code_block.ts               ≤ 250
    ├── tool_call.ts                ≤ 200
    ├── file_edit.ts                ≤ 200
    ├── checkpoint.ts               ≤ 200
    ├── attachment.ts               ≤ 100  All disabled-with-tooltip in v0.9.x
    ├── link.ts                     ≤ 120
    ├── search_result.ts            ≤ 120
    ├── pending_operation.ts        ≤ 150
    ├── history_entry.ts            ≤ 120
    ├── sidebar_empty.ts            ≤ 100
    ├── conversation_background.ts  ≤ 150
    ├── input_box.ts                ≤ 150
    └── multi_select.ts             ≤ 250

frontend/src/lib/actions/
└── contextmenu.ts                  ≤ 200  Svelte `use:contextmenu` action
```

### 3.2 Frontend — files modified (all net-shrink or constant)

- `MessageTurn.svelte`: delete existing `openMenuId` popover (~90 lines
  removed). Replace with `use:contextmenu={{target:'message', …}}`.
  Net shrink.
- `SessionList.svelte`: wire `use:contextmenu` on `sessionRow` snippet.
  Move inline delete-confirm into the new confirm store. Net shrink.
- `TagFilterPanel.svelte`: wire `target:'tag'` on sidebar rows.
- `Conversation.svelte`: **directives only** — attach `use:contextmenu`
  on conversation background, input box, message-level tag chips, code
  block wrappers, tool-call details. No handler bodies.
- `SessionEdit.svelte`, `NewSessionForm.svelte`: `target:'tag_chip'`
  on chip renderings.
- `SidebarSearch.svelte`: `target:'search_result'` on result rows.
- `+page.svelte`: mount `<ContextMenu />`, `<UndoToastHost />`,
  `<ConfirmDialog />`, `<CommandPalette />` as singletons alongside
  `<CheatSheet />`.
- `CheatSheet.svelte`: subscribe to `shortcuts.ts` so rebindings appear.
  Add rows for Shift-right-click (advanced) and
  Ctrl+Shift+right-click (native-menu passthrough).

### 3.3 Backend — new and modified files

```
src/bearings/api/
├── routes_config.py                Extend /ui-config with context_menus payload
├── routes_pending.py               NEW. Wraps bearings_dir/pending.py.
├── routes_shell.py                 NEW. /api/shell/open bridge.
├── routes_checkpoints.py           NEW. Checkpoint CRUD + fork.
├── routes_messages.py              NEW or extend. PATCH flags + DELETE.
├── routes_templates.py             NEW. Template CRUD + from-template session.
└── routes_sessions.py              Extend: PATCH pinned, bulk endpoint.

src/bearings/
├── config.py                       Add ContextMenuOverride model.
├── context_menu_config.py          NEW. Loads + validates menus.toml.
└── db/migrations/
    ├── 0022_session_pinned.sql             Phase 4 prerequisite
    ├── 0023_message_flags.sql              Phase 8 prerequisite
    ├── 0024_checkpoints.sql                Phase 7 prerequisite
    └── 0025_session_templates.sql          Phase 9b prerequisite
```

---

## 4. Backend additions by phase

### 4.1 Phase-A (blocks Phases 1-3)

- `/api/ui-config` gains `context_menus: { pinned, hidden, shortcuts }`
  merged from `~/.config/bearings/menus.toml`. Invalid IDs drop with
  WARN log.
- `/api/pending` (`GET`, `POST /{name}/resolve`, `DELETE /{name}`).
  Thin wrapper over existing `bearings_dir/pending.py`. Frontend panel
  to consume these is Phase 16 (out of scope here).
- `/api/shell/open` body `{ kind, path }`, kind ∈
  `{editor|terminal|file_explorer|git_gui|claude_cli}`. Commands come
  from `config.toml` (`shell.editor_command`, etc.). 204 on success,
  400 if unconfigured. Unlocks the `open_in` submenu everywhere a
  path exists.
- 501 stubs for every planned-but-unbuilt action, so
  frontend handlers POST and get a predictable status for the stub
  toast (per CLAUDE.md: "route bodies return 501 until backed").

### 4.2 Phase-B (checkpoints + flags)

Migrations:

- `0022_session_pinned.sql` — `sessions.pinned INTEGER NOT NULL DEFAULT 0`.
  (No `archived_at` — decision §2.2.)
- `0023_message_flags.sql` — `messages.pinned`, `messages.hidden_from_context`,
  both `INTEGER NOT NULL DEFAULT 0`.
- `0024_checkpoints.sql` —
  `checkpoints(id, session_id, message_id, label, created_at)`
  + index `(session_id, created_at)`, FK cascade on session,
  `ON DELETE SET NULL` on message.

Routes:

- `POST|GET /sessions/{id}/checkpoints`, `DELETE .../{cid}`.
- `POST /sessions/{id}/checkpoints/{cid}/fork` — copies messages up to
  checkpoint into a new session via the import pathway.
- `PATCH /messages/{id}` body `{ pinned?, hidden_from_context? }`.
  (Content-edit stays 501 — rewrites history; deferred.)
- `DELETE /messages/{id}` — real single-message delete (cleaner than
  reorg-move-to-trash).
- `PATCH /sessions/{id}` extended with `pinned`.

Agent layer:

- `agent/prompt.py` assembler filters out `hidden_from_context=1` messages
  when building the context window.
- `agent/session.py` replay/resume paths apply the same filter.

### 4.3 Phase-C (bulk + templates)

- `0025_session_templates.sql` —
  `session_templates(id, name, body, tag_ids_json, created_at)`.
- `POST /sessions/bulk` `{ op, ids, payload }` with ops `tag | untag |
  close | delete | export`. One endpoint, one audit hook.
- `GET|POST /templates`, `DELETE /templates/{id}`,
  `POST /sessions/from_template/{id}`.

### 4.4 Deferred (v0.10.x+)

- Attachments (entire subsystem — storage, table, routes, UI).
- Retry tool call / regenerate from message (agent-runner surface
  changes; non-trivial).
- Pending-operation panel UI (backend exists from Phase-A; menu target
  stays dark until panel lands).

---

## 5. Phased delivery

Relative sizing: S / M / L / XL. Each phase ships to main and is
user-visible. Version targets assume Bearings is at v0.8.0 today.

### v0.9.0-alpha — skeleton

**Phase 1** (S) — Core primitive: `ContextMenu`, `ContextMenuItem`,
`types`, `registry`, `positioning`, `contextmenu` Svelte action.
Action set = two copy actions (session id, message id). Proves
plumbing.

**Phase 2** (M) — Positioning + keyboard: viewport flip, submenu flip,
arrow/Enter/Esc/mnemonic FSM. Unit tests carry the weight.

**Phase 3** (M) — Destructive confirm + undo toast + stub toast:
`ConfirmDialog`, `UndoToastHost` (factoring the existing
`ReorgUndoToast` into a reusable base), `StubToast`, stores, and
the session-scoped don't-ask-again set.

### v0.9.1 — productive cut

**Phase 4a** (L) — Session + tag + tag-chip menus. Every spec action
either works (routes exist) or stubs (501) or disables-with-tooltip
(no primitive). Backend prereq: Phase-A (shell + ui-config extension).

**Phase 4b** (M) — Command palette Ctrl+Shift+P. Reuses registry. See
§2.4.

**Phase 5** (L) — Message + tool call menus. Absorbs and deletes
`MessageTurn.svelte`'s `openMenuId` popover. Pin/hide actions are
disabled-with-tooltip until Phase 8.

**Phase 6** (M) — Code block + file edit + link menus. Requires
`/api/shell/open` + config keys `shell.editor_command`,
`shell.terminal_command`, etc.

### v0.9.2 — deep features

**Phase 7** (XL) — Checkpoint primitive: migration 0024 + CRUD + fork
route + UI chips in conversation gutter. Un-disables all checkpoint
actions. Ships its own minor bump because of DB change.

**Phase 8** (M) — Message flags: migration 0023 + `PATCH /messages`
wiring + prompt assembler filter + runner filter. Un-stubs the
Phase-5 pin/hide stubs.

**Phase 9a** (L) — Session multi-select (Shift-click range, Cmd-click
toggle) + bulk endpoint `POST /sessions/bulk`. Un-disables the
`multi_select` target.

**Phase 9b** (M) — Session templates: migration 0025 + template CRUD
+ "Extract as template" action.

### v0.9.3 — customization + polish

**Phase 10** (M) — TOML customization: `toml-loader`, `/ui-config`
extension, `context_menu_config.py`, docs enumerating every action ID.
Server restart required to reload (hot-reload deferred).

**Phase 11** (M) — Touch + coarse pointer: long-press 500ms, 44px
targets, bottom-sheet submenus under `@media (pointer: coarse)`.

**Phase 13** (S) — Ctrl+? help mode: extend `CheatSheet.svelte` with
"all context-menu shortcuts" tab via `shortcuts.ts` subscription.

### v0.10.x+ — deferred

**Phase 14** — Attachments subsystem (entire).
**Phase 15** — Retry tool call / regenerate message.
**Phase 16** — Pending-operation frontend panel (backend already live
from Phase-A).

### Minimum viable cut per phase

- End Phase 3: right-click on session or message copies its id. Zero
  breakage. Day-one value.
- End Phase 4b: users can right-click sessions / tags and also find any
  action via Ctrl+Shift+P. Discoverability landed.
- End Phase 6: the productive cut — most right-clicks do something
  real.
- End Phase 9b: multi-select, checkpoints, templates, flags. The
  "live-in-this-app-for-years" promise cashes.
- End Phase 13: feature-complete per the shippable portion of the
  spec.

---

## 6. Cross-cutting concerns

### 6.1 Positioning

Pure function `computePlacement({ anchorRect, menuSize, viewport,
preferredSide? })`. Prefer below-right; flip horizontally / vertically
/ submenu-side when an edge overflows; clamp 4px min margin. Unit test
all eight corner + submenu cases.

### 6.2 Keyboard

Pure reducer `reduce(state, event, items)` over
`{ focusedIndex, submenuOpen, submenuFocusedIndex }` with events
`ArrowUp|Down|Left|Right|Enter|Escape|Mnemonic`. Mnemonic is an
explicit `mnemonic` field on each action (auto-derivation fights TOML
overrides). All transitions unit-tested.

### 6.3 Async submenu data

- Prefetch on 150ms hover of parent item, not on menu open.
- Spinner row while pending.
- Subscribe to store, don't snapshot — "Add tag ▸" must live-update if
  a tag is created mid-open.

### 6.4 Touch

`touch.ts` detects `pointer: coarse` via `matchMedia`. Binds
`pointerdown`, runs 500ms timer, cancels on >8px movement, dispatches
synthetic open-menu event on expiry. Coarse-mode menu renders as
bottom sheet; submenus replace parent with a "Back" item first.

### 6.5 Precedence rules on touch / mouse

- Anchor elements: right-click defers to browser native (more useful
  for "open in new tab"). Long-press opens ours.
- Text selection in message body: if selection is non-empty AND target
  is code block or message body, show ours with selection-aware
  actions at top.
- Input box (textarea): always defer to native on right-click (spell
  check, paste). Long-press opens ours (insert template, attach).
- Shift-right-click: advanced mode (see §2.5).
- Ctrl+Shift+right-click: native menu (see §2.5).

### 6.6 Stub + disabled system

- Stub: `stub.svelte.ts::notYetImplemented(actionId, reason?)` pushes
  a toast. Called automatically when a mutating action's fetch
  returns 501.
- Disabled: `action.disabled(target)` returns a string → tooltip
  shown, click is a no-op. Used for "Coming in vX.Y.Z" labels
  per §2.3.

### 6.7 Destructive confirmation

- `confirm.svelte.ts` stores `pending` + `dontAskThisSession: Set<string>`.
- Set key is `"${actionId}:${targetType}"` — archiving sessions and
  deleting messages have independent suppression.
- Bulk actions show ONE confirmation with a count. Per-item confirms
  are forbidden — bulk-delete-50 must not produce 50 dialogs.
- Set is in-memory, cleared on page reload. Matches spec's
  session-scoped intent.

### 6.8 Undo toasts

- `undo.svelte.ts` — queue capped at 3, bottom-right stack.
- Any action with `undoable: { inverseHandler, windowMs? }` auto-
  enqueues after its handler resolves.
- Default window 30s to match `ReorgUndoToast`.

---

## 7. Action ID stability contract

IDs are a public API per the spec. Same care as HTTP route paths.

### 7.1 Naming

`<target>.<verb>.<qualifier?>` — lowercase, dot-separated,
TOML-friendly. Examples:

- `session.archive`
- `session.fork.from_checkpoint`
- `session.open_in.terminal`
- `message.pin`
- `message.hide_from_context`
- `code_block.open_in.editor`
- `tool_call.copy.input`

Nouns on the left, verbs on the right. No camelCase. No underscores
inside segments where a dot would do.

### 7.2 Canonical list + generation

Each `actions/<target>.ts` exports a const union of IDs.
`frontend/scripts/dump-action-ids.ts` (not built, run on demand)
generates `docs/context-menu-action-ids.md` with every ID, target,
label, shortcut, and section. This file is checked in and reviewed
on ID changes.

### 7.3 Renaming / deprecation

Action definitions accept `aliases: string[]`. The TOML loader and
tests recognize both. Using a deprecated alias logs a console warning.
Removing an alias requires a major version bump.

### 7.4 Stability test

One test per target file asserts the sorted action-IDs array matches
a frozen snapshot. CI catches unintended renames.

---

## 8. Open questions (remaining risks)

Five governing decisions closed five of the original eleven risks.
These six remain. None block Phase 1; resolve each before its gating
phase.

1. **Chrome `chrome://flags/#always-show-context-menu`**. Users with
   this flag enabled see the native menu regardless of
   `preventDefault()`. We cannot intercept. Document in README and
   CheatSheet; no code action.

2. **Touch long-press precedence, edge cases**. Link inside a code
   block: does the browser long-press (link preview) win, or does
   ours (code_block menu)? Decision proposed in §6.5 favors browser
   on anchors, but explicit tests must enforce. *Resolve before
   Phase 11.*

3. **`~/.bearings/pending.toml` panel home**. **RESOLVED 2026-04-25
   — floating card.** See §8.3.

4. **"Regenerate from this message"**. **RESOLVED 2026-04-25 — fork
   only, fresh SDK session.** See §8.4.

5. **Slash-command shortcut collision**. `CommandMenu.svelte` binds
   `/` inside textareas. If a user TOMLs a menu shortcut that
   collides, which wins? Proposed precedence: menu shortcuts bind
   on `keydown` at document level only when no input/textarea is
   focused; slash-command trigger wins inside textareas. *Test
   before Phase 10.*

6. **TOML hot-reload**. Server restart required in v0.9.x. If demand
   emerges, `watchdog` dep + file observer. Deferred.

---

### 8.3 Pending-ops panel home (resolved)

**Decision: floating card with a sidebar-header badge indicator.**
Opened via the badge, via Ctrl+Shift+P → "Show pending operations,"
or via dedicated shortcut (default `Ctrl+Shift+O`, rebindable through
`menus.toml`).

Rejected alternatives:

- **Sidebar tab** — permanent real estate for sparse data. Pending
  ops are rare in normal use; a third sidebar tab pollutes the
  steady-state UI. If usage data later shows pending ops are common
  (multi-resolve-per-day baseline), promote to sidebar tab in a
  follow-up — the floating card's data shape doesn't change.
- **Inspector tab** — wrong scope. `pending.toml` is per-installation,
  not per-session. Inspector is session-scoped. Mismatched lifetime
  would force either a confusing "global tab inside per-session
  panel" or a duplicate global panel.

Component layout (Phase 16):

```
frontend/src/lib/components/pending/
├── PendingOpsCard.svelte         ≤ 250  Floating panel, list + actions
├── PendingOpRow.svelte           ≤ 150  One row: name, summary, resolve/dismiss
└── PendingOpsBadge.svelte        ≤ 80   Header badge with count + click handler
```

Badge mounts in the sidebar header next to the existing search/new-session
icons. Hidden when count is zero. Hover shows "N pending operations" tooltip.
Card is a viewport-anchored overlay (bottom-right, similar to `UndoToastHost`),
dismisses on Esc / outside-click. Keyboard nav reuses the context-menu
keyboard FSM (`keyboard.ts`).

Action target `pending_operation` (already enumerated in §3.1) stays as
designed; right-click on a row in the floating card opens its actions
menu (Resolve / Dismiss / Copy name / Open file in editor).

### 8.4 Regenerate-from-this-message (resolved)

**Decision: fork-only for v1; rewrite-in-place is a separate disabled
action that ships later.**

Mechanics for `message.regenerate` (fork variant, ships in Phase 15):

1. Find the user-turn boundary at or before the target message.
2. Create a new session via the existing import pathway with messages
   `[1..boundary-1]` copied verbatim.
3. Send the user message at `boundary` as the first prompt of the new
   session. Fresh `sdk_session_id` minted by the SDK on first turn.
4. New session inherits parent's `model`, `tags`, `permission_mode`.
   Title prefix `↳ regen: `. Backlink stored in `sessions.fork_parent_id`
   (already present from the existing "Fork from last message" action).
5. The original session is **untouched** — its history, sdk_session_id,
   and pending tool calls all stay live. Users can compare side-by-side.

Why fork-only:

- **Avoids the rewound-history SDK problem entirely.** We never rewind
  a live SDK session; we always start fresh in a new one. The "hidden
  state in `sdk_session_id`" risk vanishes because the fork has its own
  fresh id.
- **Matches existing "Fork from last message" pattern.** Implementation
  reuses the same import pathway. Marginal new code is the
  message-N-truncation logic, not a parallel surgery system.
- **Preserves history.** Destructive in-place rewrite makes "compare
  attempt A vs attempt B" impossible. Fork makes it free.
- **Decision posture (`decision-posture.md`):** when the bandaid (in-
  place rewrite) leaves a real gap (no comparison, hidden-state risk)
  and the complete fix has bounded scope (re-use import pathway), pick
  the complete fix.

Rewrite-in-place (`message.regenerate.in_place`):

- Stays **disabled-with-tooltip** in v0.9.x and v0.10.x: "Rewrite-in-
  place coming in a later version. Use Regenerate (fork) for now."
- Lands when there's demonstrated demand AND the SDK's session-resume
  story documents a clean partial-turn rewind path. Until then, the
  destruction risk outweighs convenience.
- Action ID reserved now to prevent later collision.

Phase 15 deliverables:

- `POST /sessions/{id}/regenerate_from/{message_id}` — server-side
  truncation + import + new-session creation in one call. Returns
  new session id.
- Frontend action `message.regenerate` (un-disabled in Phase 15) calls
  the route, navigates to the new session.
- Action `message.regenerate.in_place` registered, permanently disabled
  with the v0.10.x+ tooltip.

### 8.5 Phase 14 attachments UX (resolved)

**Upload trigger placement: both.** Composer paperclip button (discoverable)
plus drag-and-drop onto the composer or conversation pane (fast for power
users). Marginal code cost — same `<input type="file">` handler reachable
from two pathways.

**MIME whitelist: images + pdf + text/code.** Specifically:

- `image/png`, `image/jpeg`, `image/gif`, `image/webp` — screenshots,
  diagrams, photos.
- `application/pdf` — Anthropic's API supports PDFs natively; common
  documentation form.
- `text/plain`, `text/markdown`, `application/json`, `text/csv`,
  `application/toml`, `application/yaml` — review-this-file workflows.
- Code-by-extension fallback (since browsers serve many code files as
  `application/octet-stream`): `.py .ts .tsx .js .jsx .svelte .vue .go
  .rs .java .kt .swift .c .cpp .h .hpp .cs .rb .php .sh .zsh .bash
  .toml .yaml .yml .ini .conf .sql .html .css .scss .xml`. Configurable
  via `attachments.allowed_extensions`.

Rejected: "everything." Binary archives, video, executables don't have
a useful Claude-API path, bloat storage, and invite security review
concerns. If demand emerges, expand the allowlist case-by-case.

**Max sizes (configurable defaults):**

- `attachments.max_file_bytes` = `10_485_760` (10 MB per file).
- `attachments.max_per_turn_bytes` = `52_428_800` (50 MB per turn).
- `attachments.max_per_turn_count` = `10`.

Anthropic supports up to 100 MB per file via the Files API; 10 MB
captures reasonable docs without enabling video uploads. Per-turn cap
prevents accidental directory-drag mass uploads.

**Storage layout under `~/.local/share/bearings/`:**

```
~/.local/share/bearings/
├── attachments/
│   └── <session_id>/
│       └── <message_id>/
│           └── <attachment_id>__<safe_filename>
```

- **Per-session locality** so "delete session → delete files" is a
  single `rmtree` on `attachments/<session_id>/`. No content-addressed
  dedup in v1 — attachments rarely repeat, and dedup adds GC complexity
  for marginal savings.
- **Filename = `<attachment_id>__<safe_filename>`.** Id prefix prevents
  collisions on duplicate uploads in the same message; the safe filename
  (sanitized via `secure_filename` rules: alnum + `._-`, truncated to
  120 chars) is preserved for human inspection in `~/.local/share`.
- **Atomic write:** stream upload to `<...>.partial`, `fsync`, rename
  to final name. Crash-safe.
- **DB table** `attachments(id TEXT PK, session_id TEXT FK, message_id
  TEXT FK, original_filename TEXT, stored_filename TEXT, mime_type
  TEXT, size_bytes INTEGER, sha256 TEXT, created_at TEXT, deleted_at
  TEXT NULL)`. Migration `0026_attachments.sql` (Phase 14).
- **Cascade:** `ON DELETE CASCADE` from `sessions` (delete session →
  delete attachment rows + directory). Message deletion soft-deletes
  rows (`deleted_at` set) but keeps the file on disk for audit until
  the session is deleted.
- **Hand-off to File Display:** the artifacts subsystem (session
  `edaae9bad976411a86e8674665a3dac4`) reuses this storage tree under
  `~/.local/share/bearings/artifacts/` (parallel directory, same shape).
  Decisions about lifetime there (per-session vs global) are
  independent of the attachments layout chosen here.

Phase 14 deliverables:

- Migration `0026_attachments.sql`.
- `routes_attachments.py`: `POST /api/sessions/{id}/attachments`
  (multipart upload), `GET /api/attachments/{id}` (stream),
  `DELETE /api/attachments/{id}` (soft-delete row, file kept).
- Frontend `Composer.svelte` extension: paperclip button +
  drag-and-drop overlay + chip list of staged attachments.
- `attachment` action target moves from "all-disabled-with-tooltip"
  (placeholder in §3.1) to fully wired with copy, save-as, delete,
  open-in-default-app actions.
- Config keys in `~/.config/bearings/config.toml` under `[attachments]`.

---

## 9. Testing strategy

### 9.1 Unit (vitest, co-located)

- `positioning.test.ts` — 8 corner × overflow combos, 4 submenu flip
  cases.
- `keyboard.test.ts` — every FSM transition; mnemonic resolution.
- `registry.test.ts` — default + TOML pinned + hidden + shortcuts
  merge order; invalid-ID drop; deprecated-alias mapping.
- `toml-loader.test.ts` — malformed TOML, unknown target, unknown
  ID, shortcut collision, pinned+hidden conflict rules.
- `confirm.svelte.test.ts` — don't-ask-again key format, cross-target
  independence.
- `undo.svelte.test.ts` — enqueue, expiry, cap at 3.
- Per-target action files: frozen ID snapshot; disabled-predicate
  wiring (e.g. `session.archive` disabled on already-closed session).

### 9.2 Integration

Playwright or testing-library flows:

- Right-click session row → Archive → destructive confirm → POST
  lands → row moves to Closed group → undo toast → click Undo →
  restored.
- Shift-right-click → advanced items visible.
- Ctrl+Shift+right-click → no custom menu, native Chrome menu fires.
- Ctrl+Shift+P → command palette opens → filter "archive" → Enter →
  fires on current session.
- Long-press on touch viewport → bottom-sheet opens.
- Keyboard-only: focus session list → Shift+F10 → arrows navigate →
  Esc closes.

### 9.3 Manual

- Visual overflow polish at every viewport corner.
- Linux (GNOME / Hyprland / KDE) right-click performance.
- Chrome "always show native menu" flag — observed behavior matches
  docs.
- Shell-open actions (spawn real `xdg-open` / `start`) — mocked in
  pytest, manual-verified in dev.

---

## 10. Critical files

- `frontend/src/lib/components/MessageTurn.svelte` — replace existing
  popover.
- `frontend/src/lib/components/SessionList.svelte` — session rows +
  sidebar_empty + future multi-select.
- `frontend/src/lib/components/Conversation.svelte` — **directive-only**
  surface for conversation_background, input_box, code_block,
  tool_call, file_edit, tag_chip. 1424 lines already; no new handler
  bodies.
- `src/bearings/api/routes_config.py` — `/ui-config` extension for
  `context_menus` payload.
- `src/bearings/db/schema.sql` + migrations 0022 (pinned), 0023
  (message flags), 0024 (checkpoints), 0025 (templates).
- `src/bearings/agent/prompt.py` — `hidden_from_context` filter at
  context-window assembly.
- `src/bearings/agent/session.py` — same filter on replay/resume.
- `src/bearings/agent/registry.py` — SDK subprocess invalidation on
  model change (decision §2.1).

---

## 11. Non-decisions (reaffirmed)

From the spec; restated for plan completeness:

- No icon-only menus. Labels always present.
- Max two submenu levels. Beyond that, a dialog.
- No inline editing in menus. Always a dialog or inline editor
  outside the menu.
- "Don't ask again" is session-scoped. Never per-installation.
- No drag-from-menu. Menus activate; drag starts elsewhere.
- No meta-menu. Right-clicking an open menu closes it and opens a new
  one at the new position.

---

## Changelog of this plan

- **2026-04-22** — Initial plan. Five governing decisions made
  (§2.1–§2.5). Target train v0.9.0-alpha → v0.9.3. Six open
  questions remain (§8).
- **2026-04-25** — Phase 14-16 product gates resolved (§8.3 floating
  card, §8.4 fork-only regenerate, §8.5 attachments UX + storage
  layout). Three of the original six open questions closed; three
  remain (Chrome flag doc, touch long-press tests, slash-command
  collision test). Phases 14-16 unblocked for execute-step
  implementation; the gating session is `d0c2b70026574cb4a1683f617a81d565`.
