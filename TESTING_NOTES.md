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

### Pending Dave's browser walkthrough

Every UI surface below should be exercised before v0.2 can be
called user-ready. Unit tests cover shape, not feel. Record
observations here and flag regressions with a version bump.

- [ ] **Inspector → Context disclosure**: opens cleanly, shows
  base-only on a fresh session, adds tag_memory layer when a
  tag with a memory is attached, adds session layer when
  session_instructions is set. Per-layer content collapsibles
  expand and stay expanded.
- [ ] **Inspector Context → session instructions editor**:
  textarea hydrates from the current session, dirty state
  surfaces Reset, Save writes via PATCH, empty content saves as
  null, switch-session discards the draft.
- [ ] **Tag sidebar ✎ → TagEdit modal**: opens with the tag's
  current state, name/pinned/sort_order/defaults/memory all
  edit cleanly, markdown preview toggle flips to rendered HTML,
  clearing the memory and saving fires DELETE, saving content
  fires PUT, Delete button takes two clicks.
- [ ] **Conversation header tag chips**: render when a session
  has tags attached, pinned tags show the ★ glyph, chip order
  matches sidebar order, hover title shows default
  working_dir/model when a tag has them.
- [ ] **New-session form**: opens with tags seeded from the
  sidebar filter, submit button disabled until ≥1 tag is
  attached, attaching a tag with defaults pre-fills
  working_dir/model, Enter on a novel tag name creates + attaches.
- [ ] **SessionEdit modal**: tag attach / detach still works
  post-v0.2; ✕ on a chip detaches without side effects.
- [x] **WS + CLI `send`** against a live agent (2026-04-20):
  session `74374ddb` tagged `infra` with memory "Prefer nftables
  over iptables…". Prompt "one-liner firewall rule that blocks
  SSH except from 10.0.0.0/8" got back `sudo nft add rule inet
  filter input tcp dport 22 ip saddr != 10.0.0.0/8 drop` —
  nftables, unprompted. `/system_prompt` confirmed 2 layers
  (base + infra tag_memory, 66 tokens). Event stream:
  `message_start` → `thinking` → `token` (coalesced) →
  `message_complete` with cost_usd=0.176.

## v0.3.1 (2026-04-20)

### Pending Dave's browser walkthrough

- [ ] **Resizable panes**: drag the handle between sidebar and
  conversation — width updates live, clamps at 200px min, snaps to
  collapsed below that, maxes out at ~50% viewport. Release persists
  the width (reload the page to confirm). Same for
  conversation/inspector handle.
- [ ] **Collapse toggles**: click the chevron button centered on
  each handle; the near pane collapses to 0px. Click again —
  pre-collapse width restored. State survives reload.
- [ ] **Keyboard resize**: Tab to a handle (sky-500 focus ring
  shows), ArrowLeft/Right nudges 16px, Shift+Arrow nudges 48px.
  Enter or Space toggles collapse. For left handle, ArrowRight
  widens sidebar; for right handle, ArrowLeft widens inspector.
- [ ] **Collapse persistence across sessions**: collapse both
  sides, reload — they stay collapsed. Expand, reload — widths
  return to the last-dragged values.
