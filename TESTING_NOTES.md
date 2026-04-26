# Testing Notes

## v0.1.37 (2026-04-19, server http://127.0.0.1:8787, auth off)

- **[fixed in v0.1.38]** Prompt send was bound to `⌘/Ctrl+Enter` with
  Enter inserting a newline — reversed now: Enter sends, Shift+Enter
  newlines. Matches chat UI conventions (ChatGPT / Claude / Slack).
  CheatSheet and placeholder updated to match.
- **[fixed in v0.1.38]** Inspector tool-call list was flat — now
  nested under an "Agent" collapsible disclosure with model subtitle
  and a running-count badge; the aside auto-scrolls to the latest
  tool call while the agent is streaming (and the disclosure is
  open).

## v0.2.13 (2026-04-19)

### Verified programmatically

These are confirmed by the automated gates, not by browser use.

- **Migrations 0006–0009 apply in order on a fresh DB.** Covered by
  `init_db` running all migrations at test fixture setup; 168
  backend tests + a clean `pytest`.
- **Prompt assembler produces 3 layers** (base → tag memories →
  session instructions), precedence matches pinned/sort_order/id,
  tag-without-memory is silently skipped, session_instructions
  always last. 8 cases in `test_prompt_assembler.py`.
- **`/api/sessions/{id}/system_prompt`** returns the same layered
  shape the agent sends to the SDK. Full-stack case in
  `test_tag_memories.py::test_system_prompt_full_stack`.
- **`POST /api/sessions` rejects `tag_ids: []` and unknown tag ids
  with 400.** Two cases in `test_routes_sessions.py`.
- **Tag memories CRUD round-trips** (GET/PUT/DELETE on
  `/api/tags/{id}/memory`), and delete-tag cascades to
  `tag_memories` via FK. 13 cases in `test_tag_memories.py`.
- **Tag defaults round-trip** on create + partial update; explicit
  null clears. 5 cases in `test_tags.py`.
- **AgentSession passes assembled prompt as
  `ClaudeAgentOptions.system_prompt`** when `db=conn` is wired,
  omits it when `db=None`. 2 cases in `test_agent_session.py`.

### Pending Dave's browser walkthrough — DEFERRED to pre-1.0.0

**Status (2026-04-21):** Deferred to a single pre-1.0.0 regression
pass. App is at v0.3.22; these checklists were written against the
v0.2.13 surface and the UI has moved on (Inspector tabs,
conversation header, new-session form, and tag edit modal have all
been reshaped multiple times since). Rewrite this checklist against
the *then-current* UI immediately before cutting 1.0.0 — don't
exercise the stale copy below.

The one positive observation worth preserving:

- [x] **WS + CLI `send`** against a live agent (2026-04-20):
  session `74374ddb` tagged `infra` with memory "Prefer nftables
  over iptables…". Prompt "one-liner firewall rule that blocks
  SSH except from 10.0.0.0/8" got back `sudo nft add rule inet
  filter input tcp dport 22 ip saddr != 10.0.0.0/8 drop` —
  nftables, unprompted. `/system_prompt` confirmed 2 layers
  (base + infra tag_memory, 66 tokens). Event stream:
  `message_start` → `thinking` → `token` (coalesced) →
  `message_complete` with cost_usd=0.176.

## v0.3.1 / v0.3.3 browser walkthroughs — DEFERRED to pre-1.0.0

Pane-resize (v0.3.1) and TagEdit/NewSessionForm picker (v0.3.3)
checklists folded into the single pre-1.0.0 regression pass noted
above. Leaving the historical spec here for reference, but **do
not run these as-is** — the UI has changed since and the list
should be rewritten against the 1.0.0-candidate surface.

<details>
<summary>Historical v0.3.1 / v0.3.3 checklist (stale)</summary>

### v0.3.1 — resize & collapse

- **Resizable panes**: drag the handle between sidebar and
  conversation — width updates live, clamps at 200px min, snaps
  to collapsed below that, maxes out at ~50% viewport. Release
  persists the width (reload the page to confirm). Same for
  conversation/inspector handle.
- **Collapse toggles**: click the chevron button centered on
  each handle; the near pane collapses to 0px. Click again —
  pre-collapse width restored. State survives reload.
- **Keyboard resize**: Tab to a handle (sky-500 focus ring
  shows), ArrowLeft/Right nudges 16px, Shift+Arrow nudges 48px.
  Enter or Space toggles collapse. For left handle, ArrowRight
  widens sidebar; for right handle, ArrowLeft widens inspector.
- **Collapse persistence across sessions**: collapse both
  sides, reload — they stay collapsed. Expand, reload — widths
  return to the last-dragged values.

### v0.3.3 — TagEdit / NewSessionForm pickers

- **TagEdit "Order" relabel**: open `infra` ✎ — the field
  previously labeled "Sort" now reads "Order". Hover the input
  for the tooltip "Lower number = higher in sidebar. Breaks ties
  in prompt assembly (later wins)."
- **TagEdit ModelSelect**: the Default model field is a
  dropdown showing `claude-opus-4-7` / `claude-sonnet-4-6` /
  `claude-haiku-4-5-20251001` / `Custom…`. Picking a known model
  stores it. Picking Custom clears the value and reveals a
  free-text input with focus. For a tag whose default_model is
  already an unknown id (e.g. a dated snapshot), the modal opens
  in Custom mode with the input pre-populated.
- **TagEdit FolderPicker**: the Default working dir field has
  a text input + "Browse" button. Browse opens an inline tree:
  breadcrumb at top (each segment is clickable to jump),
  ⬆ parent, hidden-dir toggle, grid of subdirectory buttons.
  Click a subdir to descend; breadcrumb updates. "Use this
  folder" writes the current path back to the input and closes
  the picker. A bad path (`/nope`) surfaces "not found" inline
  without clobbering the input.
- **NewSessionForm pickers**: same ModelSelect + FolderPicker
  in the + session form. Attaching a tag with defaults still
  prefills both fields (working_dir only when empty, model
  unconditionally per last-wins).
- **`/api/fs/list` live smoke**: run `curl -s
  "http://127.0.0.1:8787/api/fs/list?path=$HOME" | jq` —
  returns `{path, parent, entries[]}` with hidden dirs omitted.
  Add `&hidden=true` to include them. `path=./relative` → 400,
  `path=/nonexistent` → 404.

</details>

## Pre-1.0.0 browser regression pass — TODO

Single consolidated walkthrough to run immediately before cutting
1.0.0. Rewritten 2026-04-26 against the v0.20.7 1.0.0-candidate UI.
The stale v0.2 / v0.3 history above is preserved in `<details>`
blocks for reference but **must not be run as-is** — feature surface
has expanded substantially (tags v0.2, permission profiles v0.4,
checkpoints / templates / vault / paired chats / live todos
v0.6→v0.9, finder-click filter v0.10, token-cost survival kit v0.12,
`bearings todo` CLI v0.13, themes v0.14, keyboard shortcuts v0.15,
context menu + tool-output linkifier v0.16, intra-call tool-output
streaming + Conversation split v0.17, settings rewrite v0.20.6).

Run the items below in order. Each section maps to a concrete UI
surface or component pair; file references point at the current
codebase so a regression in any one item is bisectable.

### 1. Three-pane shell (`+layout.svelte`, `+page.svelte`)

- **Resize handles**: drag the sidebar↔conversation handle and the
  conversation↔inspector handle. Width updates live, clamps at 200px
  min, snaps collapsed below that, maxes near ~50% viewport. Release
  + reload preserves the dragged width.
- **Collapse toggles**: click the chevron centered on each handle —
  near pane collapses to 0px, click again restores the pre-collapse
  width. State survives reload.
- **Keyboard resize**: Tab onto a handle (sky-500 focus ring),
  ArrowLeft/Right nudges, Shift+Arrow nudges larger, Enter/Space
  toggles collapse.
- **Both panes collapsed → reload** stays collapsed; expand → reload
  returns to last-dragged widths.

### 2. Sidebar — session list, tags, search, new-session

- **`SessionList.svelte` live updates**: open the page in two
  windows, send a prompt in window A, window B's sidebar updates
  the running-set indicator without a manual refresh (WS broadcast
  via `ws_sessions.py`).
- **`SidebarSearch.svelte`**: type in the search field — list
  filters live, matches highlight, clearing restores full list.
- **`TagFilterPanel.svelte` OR semantics**: with two pinned tags,
  click both — sidebar shows the union (sessions tagged with EITHER),
  not the intersection. Pinned tags appear above unpinned.
  Right-click a tag row to surface its context menu (edit / unpin /
  delete).
- **Finder-click filter (v0.10)**: ⌘/Ctrl-click a tag chip on a
  session row in the conversation header → sidebar filters to that
  tag only.
- **`NewSessionForm.svelte`**: open the new-session form, attach a
  tag with `default_model` and `default_working_dir` set — both
  fields prefill (working_dir only when empty, model unconditionally
  per last-wins). FolderPicker browse → breadcrumb navigation,
  hidden-dir toggle, "Use this folder" writes back. Submit creates
  a session that appears in the sidebar with the chosen tags.
- **`SessionEdit.svelte`**: ⋯ → Edit on a session row → modal opens
  with title / description / budget / tag attach-detach. Save
  round-trips and the sidebar row reflects changes.

### 3. Conversation header (`ConversationHeader.svelte`)

- **Title editable inline** — click → edit → blur saves; Esc cancels.
- **Tag chips** render in the header, click opens the tag's filter
  view (see §2 finder-click).
- **Cost / budget readout** — running cost in USD; a `max_budget_usd`
  set via SessionEdit shows a progress fragment. Cross-check against
  `GET /api/sessions/{id}` and `/metrics`.
- **`ContextMeter.svelte` color bands** — verify the actual band
  thresholds at ship time; the v0.20.7 palette is slate (default) →
  amber (warm) → orange (warning) → red (critical). Bands recompute
  live as turns stream.
- **System-prompt viewer disclosure** — open it; the layer list
  matches `/api/sessions/{id}/system_prompt` (base, tag_memories
  ordered by pinned/sort_order/id, session_description,
  session_instructions). Token totals per layer match the API.

### 4. Conversation messages (`Conversation.svelte`,
    `MessageTurn.svelte`)

- **Markdown + code highlighting**: send a prompt that returns a
  Python and a SQL block — both render with shiki highlighting,
  copy-button on each block works.
- **Live tool-call streaming (v0.17)**: prompt something that runs
  Bash/Read/Grep; tool-call output streams into the turn intra-call,
  not just on completion. The matching entry appears in the
  Inspector tool-call list as it streams.
- **Tool-output linkifier (v0.16)**: file paths in tool output
  render as clickable links and resolve to a viewer or the matching
  artifact.
- **Assistant-reply action row** (Wave 1 + 2, `MessageTurn.svelte`):
  on a finished assistant turn the row shows
  `[ℹ MORE] [＋ SPAWN] [✂ TLDR] [⚔ CRIT] [⎘ COPY]`.
  - `ℹ MORE` opens the elaborate flow.
  - `＋ SPAWN` creates a new chat-kind session seeded with the
    reply, inheriting parent tags + working_dir, and selects it.
  - `✂ TLDR` opens `ReplyActionPreview.svelte`, streams a TL;DR,
    Copy / Close / Send-to-composer all work.
  - `⚔ CRIT` opens the same modal with critique output, distinct
    header label.
  - `⎘ COPY` copies the raw reply.
- **Per-turn ⋯ context menu** (`context-menu/ContextMenu.svelte`):
  Move (to another session) and Split (start a new session at this
  turn) both work. Move shows `SessionPickerModal.svelte`.
- **Bulk-select mode** (`BulkActionBar.svelte`): shift-click to
  select a range, bulk Move / Delete via the toolbar.
- **`ReorgUndoToast.svelte`**: after a Move/Split, undo toast
  appears; clicking Undo restores prior state, dismisses on timeout.
- **`ReorgAuditDivider.svelte`** renders between turns moved across
  reorg events with a timestamp + source-session label.
- **`CheckpointGutter.svelte`**: turn gutter shows checkpoint dots;
  click → restore via `routes_checkpoints.py`.

### 5. Composer (`ConversationComposer.svelte`)

- **Enter sends, Shift+Enter newline** (per v0.1.38 fix).
- **Slash-command palette**: type `/` at start of a message — palette
  opens with available commands from `routes_commands.py`. Arrow
  keys + Enter inserts.
- **File attachments**: drag-drop a file into the composer, paste
  a screenshot from clipboard, click the paperclip — all three
  paths produce `[File N]` tokens with the real path preserved as
  sidecar metadata. Upload-status overlay shows progress.
- **Draft history**: ArrowUp on an empty composer cycles previous
  drafts.
- **Permission-mode selector** (`PermissionModeSelector.svelte`):
  switching auto/ask/always/deny on a turn affects the next
  tool-call approval flow.

### 6. Inspector (`Inspector.svelte`)

- **Context disclosure + layer editors**: the layered prompt
  preview matches `/api/sessions/{id}/system_prompt`; clicking a
  layer with an editor (session_description,
  session_instructions, tag memory) opens an inline edit; save
  round-trips.
- **Tool-call list**: streams entries as they fire, auto-scrolls to
  latest while open, shows agent name + running count badge (v0.1.38
  shape).
- **Approval broker UI** (`ApprovalModal.svelte`): with a
  permission profile that asks before tool execution, run a
  prompt that triggers Bash; the modal opens with command preview,
  Allow / Deny both terminate cleanly.
- **`AskUserQuestionModal.svelte`**: agent-driven user-input
  prompts surface a modal; submitting injects the answer back
  into the agent loop.
- **Pending ops** (`PendingOpsCard.svelte`,
  `PendingOpsBadge.svelte`): long-running operations show in the
  pending card; cancel works.
- **Live TodoWrite card** (`LiveTodos.svelte`): pinned at top of
  conversation when the agent has emitted a `TodoWrite`; tri-state
  glyphs update live as the agent ticks items.

### 7. Tags (`TagFilterPanel.svelte`, `TagEdit.svelte`)

- **TagEdit modal** opens with: name, pinned toggle, order field
  (tooltip "Lower number = higher in sidebar; breaks ties in prompt
  assembly, later wins"), default_model dropdown (ModelSelect with
  Custom… branch), default_working_dir (FolderPicker), markdown
  memory editor with preview, delete button.
- **Memory markdown preview** renders headers / lists / code on the
  preview tab.
- **Delete cascades** to `tag_memories` (verify via SQL or the
  re-opened modal not surfacing the memory).

### 8. Checklists (`ChecklistView.svelte`,
    `ChecklistChat.svelte`)

- A `kind="checklist"` session opens the checklist surface, not
  the conversation surface. `kind="chat"` opens the conversation
  surface; `POST /checklist/items` against a chat-kind session
  returns 400 (covered by API tests, but the UI should never
  surface that error to a user).
- **Item nesting**: parent/child cascade works — checking a parent
  cascades down or warns, per current cascade rule.
- **Paired-chat link** (💬 button): opens the linked chat session
  in a side context; spawning a new linked chat via the action
  creates a sibling row in the sidebar tagged with the parent's
  tags.
- **`ChecklistChat.svelte`**: the embedded compact chat above the
  checklist receives messages and persists per item.

### 9. Settings (`Settings.svelte`,
    `settings/SettingsShell.svelte`, v0.20.6 rewrite)

- Open Settings → left nav rail lists Profile / Appearance /
  Defaults / Notifications / Authentication / About.
- **Profile**: display name auto-saves on blur.
- **Appearance**: theme picker — switch theme, meta-theme-color
  updates, change persists across reload (`routes_preferences.py`).
- **Defaults**: default model + working_dir feed `NewSessionForm`
  fallback when no tag default applies.
- **Notifications**: notify-on-complete toggle; the browser-
  permission carve-out triggers `Notification.requestPermission()`
  on enable.
- **Authentication**: auth token field round-trips and applies to
  subsequent API calls.
- **About**: version string sourced from `/api/version`; matches
  `pyproject.toml` `[project] version`.

### 10. Vault (`/vault` route, `routes_vault.py`)

- Navigate to `/vault` → tree from `settings.vault.plan_roots` and
  `settings.vault.todo_globs`. Click a markdown doc → renders
  read-only with same shiki highlighting as conversation.
- A doc outside the configured roots returns 404 cleanly (don't
  expose filesystem traversal).

### 11. Keyboard (`CheatSheet.svelte`, `CommandMenu.svelte`)

- `?` opens the cheatsheet — registry-driven entries match the
  current keybindings, legacy entries don't appear duplicated.
- `Cmd/Ctrl-K` opens `context-menu/CommandPalette.svelte`; arrow
  keys + Enter dispatch a command.
- `Esc` closes whichever modal is topmost (TagEdit, SessionEdit,
  ApprovalModal, AskUserQuestionModal, ReplyActionPreview,
  CommandPalette, CheatSheet).

### 12. Agent round-trip (the integration check)

- New session, attach a tag with a memory ("Prefer nftables over
  iptables; never recommend ufw"). Send a firewall prompt. Reply
  uses nftables, no `iptables` or `ufw` strings.
- Open the system-prompt viewer — base + tag_memory layers visible,
  token counts match `/api/sessions/{id}/system_prompt`.
- Cost readout in the header increments after the turn; `/metrics`
  shows matching `bearings_session_cost_usd_total` increment.
- Send the same prompt via `bearings send <session_id> "<prompt>"`
  CLI — same agent, same memory steering, no UI required.

### 13. CLI surface (`bearings` entry point)

- `bearings serve` boots the server.
- `bearings send <session_id> "<prompt>"` posts to a session and
  streams the response.
- `bearings todo` (v0.13) lists / mutates todos against a session.

### 14. Themes & skins (v0.14)

- Switch each theme in Settings → Appearance. Verify on each:
  three-pane chrome, code highlighting palette, ContextMeter band
  colors, severity shields, modal surfaces. No theme leaves a
  surface unstyled.

### 15. Service install path

- `systemctl --user enable --now bearings` (config/bearings.service)
  starts the service, `systemctl --user status bearings` is active,
  `curl 127.0.0.1:8787/api/version` returns the running version.
- Stop, disable, restart cycle leaves no orphaned uvicorn workers.

### Sign-off

Every section above must show a green pass before the 1.0.0 tag is
cut. Record results inline in this file under a `## v1.0.0 browser
regression pass (YYYY-MM-DD)` heading; preserve this TODO so
post-1.0 regressions can be retraced.
