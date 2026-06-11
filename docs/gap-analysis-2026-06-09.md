# Bearings v1 — Gap Analysis (2026-06-09)

Synthesised from: `~/.claude/plans/bearings-parity-gaps.md`,
`~/.claude/plans/bearings-gap-closure-pipeline.md`,
`~/.claude/plans/bearings-production-pipeline.md`,
`TODO.md` (v1 repo), `TODO.md` (archive v0.17.x),
and direct inspection of `frontend/src/` + `src/bearings/` at HEAD (v1.2.0).

---

## 1. Plan-file tracking drift (must fix before next pipeline)

These files are the authoritative tracking documents; all three are stale.

### 1a. `~/.claude/plans/bearings-v1-rebuild.md` — **MISSING**

Every reference doc (CLAUDE.md, parity-gaps.md, gap-closure-pipeline.md)
cites this as the master 29-item build order. The file does not exist on disk.
It was either never written under that slug, archived under a different name,
or deleted. The `.archive/` directory under `~/.claude/plans/` contains
several time-stamped plan files but none identifiable as the rebuild master.

**Action:** Locate or recreate. If irretrievably lost, document the current
state (v1.2.0 shipped, parity achieved) as a replacement summary and update
the CLAUDE.md reference.

---

### 1b. `~/.claude/plans/bearings-parity-gaps.md` — **SEVERELY STALE**

Completion table as written (last updated ~2026-06-04):

| Tier | Total | Done | Remaining |
|------|-------|------|-----------|
| T0   |   1   |   1  |     0     |
| T1   |  12   |   2  |    10     |
| T2   |  14   |   3  |    11     |
| T3   |   8   |   3  |     5     |
| **Total** | **35** | **9** | **26** |

**Actual state after v1.2.0 (verified against codebase and CHANGELOG):**
Every item marked `[ ]` is implemented. See §3 below for the full audit.
The table should read 35/35 done.

---

### 1c. `~/.claude/plans/bearings-gap-closure-pipeline.md` — **STALE**

Status header reads `⚙️ PENDING LAUNCH` but the pipeline ran and produced
v1.2.0 (2026-06-04). Exec-0 through Exec-6 all completed. The file needs
its status updated to `✅ COMPLETE` and the orchestrator session ID filled in.

---

## 2. Genuinely open technical items

These are not tracked in parity-gaps.md and were not resolved by 1.2.0.

### 2a. SDK supervisor initialize timeout (unknown root cause)

**Source:** `TODO.md` §"Open follow-ups from the 2026-05-03 stuck-session diagnosis"
**Status:** Open. No root-cause fix. Last checked 2026-06-02: no commits found.

The SDK's `_send_control_request("initialize")` timed out once in a
long-running server process. Direct out-of-process probes with identical
options complete in < 2s. The failure is process-state-dependent. Three
plausible causes remain uninvestigated:

1. File-descriptor / stdio inheritance sensitivity when the parent process
   has many active WS subscribers.
2. Concurrent supervisor spawn lock race on near-simultaneous POSTs to
   distinct sessions.
3. SDK ↔ `claude` CLI version skew (pin `~=0.1.69` vs CLI at the time).

The reliability fix in 1.2.0 (`_make_task_exception_logger`, `done_callback`
wired) surfaces future hangs in structlog, but does not prevent them.

**When it recurs:** capture the `sdk_loop` `_log.warning` from journald
before touching anything. That traceback is the only diagnostic.

---

### 2b. Daily-probe `/api/usage/headroom` endpoint

**Source:** `TODO.md` §"Daily-probe /api/usage/headroom endpoint swap"
**Status:** Open (low urgency; functionally covered).

Master checklist item B.1 names `/api/usage/headroom` in its done-when
criteria. That endpoint does not exist in v1 (`/api/quota/current` and
`/api/quota/history` cover the same surface). The probe uses the quota
endpoints. If a `/headroom` route is ever added: swap the probe rows,
drop this entry.

---

### 2c. Chrome Wayland drag-and-drop (hardware/compositor wall)

**Source:** `TODO.md` (archive) §"Drag-and-drop browser compatibility"
**Status:** Open (not fixable client-side).

Chrome on Hyprland+Wayland never dispatches `drop` events to any target,
even under `--ozone-platform=x11`. The problem is in Chromium's Wayland
and XDND paths, not Bearings. Workarounds already shipped (Ctrl+V paste,
📁 browse button). Future check: `--enable-features=FileSystemAccessDragAndDrop`
when Chromium ships a Wayland fix.

The `drop` receiver, `parseUriList`, `extractPaths`, and `dropDiagnostic`
banner must NOT be removed — they surface future regressions.

---

### 2d. Transcript [File N] chip rendering (v0.17.x carry-forward)

**Source:** `TODO.md` (archive) §"Terminal-style [File N] attachments"
**Status:** Unresolved carry-forward from v0.17.x; v1 status unverified.

In v0.17.x the user bubble rendered stored `[File N]` text literally
(not as styled chips). `parseMessageBody` in `lib/attachments.ts` was
ready to walk the message; the user bubble renderer needed to iterate
segments and emit styled chip spans. Whether v1 `MessageTurn.svelte`
resolves this or still renders bare tokens — needs a visual check.

---

### 2e. SSH proxy git push blocker (operational sysadmin wall)

**Source:** `TODO.md` §"Push backlog — SSH proxy config permissions"
**Status:** Persistent operational issue. Requires a real root shell.

`git push` fails with `Bad owner or permissions on
/etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf`. The directory is
owned by `nobody:nobody` (systemd regression). The workaround is
`git -c core.sshCommand='ssh -F ~/.ssh/config' push …` (confirmed
working from the agent sandbox). The durable fix requires:

```bash
sudo chown root:root /etc/ssh/ssh_config.d /etc/ssh/ssh_config.d/*
```

Run from a real host shell (not the agent — `NoNewPrivs` may block it).

---

### 2f. `bearings status` / `bearings log` / `bearings pending list` CLI polish

**Source:** `TODO.md` (archive v0.17.x) §"v0.6.3+ polish"
**Status:** Open (v1 CLI exists; polish items deferred).

Color output, terminal-aware formatting, `--last N` flag. The commands
exist in the `cli/` package; the deferred polish items were never
prioritised.

---

## 3. Parity-gaps.md audit — all items verified as implemented

Each `[ ]` item from `bearings-parity-gaps.md` audited against HEAD.

| Item | Plan status | Actual status | Evidence |
|------|-------------|---------------|----------|
| T1-03 auto-title suggest | `[ ]` | ✅ DONE | CHANGELOG 1.2.0 Exec-5; `preview_session_title` route |
| T1-04 message.fork | `[ ]` | ✅ DONE | `MessageTurn.svelte` `MENU_ACTION_MESSAGE_FORK_FROM_HERE` handler wired; creates checkpoint then forks |
| T1-05 message.edit | `[ ]` | ✅ DONE | `MessageTurn.svelte` `MENU_ACTION_MESSAGE_EDIT` handler; user-role only |
| T1-06 code_block.run | `[ ]` | ✅ DONE | `markdownContextMenu.ts` wires `MENU_ACTION_CODE_BLOCK_RUN` → `pasteIntoComposer` when `sessionId` provided |
| T1-07 tool_call.retry/debug/edit | `[ ]` | ✅ DONE | `ToolOutput.svelte` wires all three handlers; retry sends prompt, edit opens input textarea, debug toggles JSON drawer |
| T1-08 checkpoint.compare | `[ ]` | ✅ DONE | `CheckpointGutter.svelte` `MENU_ACTION_CHECKPOINT_COMPARE` handler; `CheckpointCompareModal.svelte` component |
| T1-09 reply actions | `[ ]` | ✅ DONE | CHANGELOG 1.2.0 Exec-5; `reply_actions.py` route + `ReplyActionPreview.svelte` |
| T1-10 Inspector Files tab | `[ ]` | ✅ DONE | CHANGELOG 1.2.0 Exec-3 (CHANGELOG labels it "Exec-3" per pipeline Exec-4 content) |
| T1-11 Inspector Changes tab | `[ ]` | ✅ DONE | Same as above |
| T1-12 change_model submenu | `[ ]` | ✅ DONE | CHANGELOG 1.2.0 Exec-5; `MENU_ACTION_SESSION_CHANGE_MODEL` in registry with `submenu: true` |
| T2-01 Artifacts API | `[ ]` | ✅ DONE | CHANGELOG 1.2.0 Exec-2A; `artifacts.py` route (`GET /api/sessions/{id}/artifacts`) |
| T2-02 UI config endpoint | `[ ]` | ✅ DONE | CHANGELOG 1.2.0 Exec-2A; `GET/PATCH /api/ui-config` |
| T2-03 History export | `[ ]` | ✅ DONE | CHANGELOG 1.2.0 Exec-2A; `GET /api/sessions/{id}/history/export` |
| T2-07 Spawn classify | `[ ]` | ✅ DONE | CHANGELOG 1.2.0 Exec-2B; `sessions_classify.py` route |
| T2-08 Work evidence | `[ ]` | ✅ DONE | `sessions_io.py` route `GET /api/sessions/{session_id}/work_evidence`; `WorkEvidenceOut` model in `sessions.py` |
| T2-09 Settings sections | `[ ]` | ✅ DONE | `NotificationsSection.svelte`, `PrivacySection.svelte`, `HelpSection.svelte`, `AboutSection.svelte` all present; test files exist |
| T2-10 Bulk title suggest modal | `[ ]` | ✅ DONE | CHANGELOG 1.2.0 Exec-5 |
| T2-11 copy_code / copy_json | `[ ]` | ✅ DONE | `MessageTurn.svelte` both handlers wired; `extractCodeBlocks` and `extractJson` functions |
| T2-12 Multi-select context menus | `[ ]` | ✅ DONE | `MessageTurn.svelte` `multiSelectMenuHandlers` wired for copy/delete/pin/hide |
| T2-13 Attachment context menus | `[ ]` | ✅ DONE | `SentAttachmentChips.svelte` and `Composer.svelte` wire copy_path, copy_filename, open_in_editor, remove |
| T2-14 Pending op context menus | `[ ]` | ✅ DONE | `PendingOpRow.svelte` wires resolve/dismiss/copy_name/copy_command/open_in_editor |
| T3-01 Severity tag auto-seeding | `[ ]` | ✅ DONE | CHANGELOG 1.2.0 Exec-3 |
| T3-02 Billing mode display | `[ ]` | ✅ DONE | CHANGELOG 1.2.0 Exec-3 |
| T3-03 SpawnClassifiedCard | `[ ]` | ✅ DONE | CHANGELOG 1.2.0 Exec-5 |
| T3-07 error_pending sidebar pip | `[ ]` | ✅ DONE | CHANGELOG 1.2.0 Exec-3 |
| T3-08 History export (portability) | `[ ]` | ✅ DONE | Covered by T2-03 / T2-08 |

**Conclusion: parity-gaps.md completion table should read 35/35 (100%).**

---

## 4. Archive v0.17.x TODO items — applicability to v1

The archive TODO (`/home/beryndil/Projects/archive/bearings-v0.17.x/TODO.md`)
is a 2544-line history document. Most items are v0.17.x-specific. Items with
potential v1 carry-forward:

| Archive item | v1 status |
|---|---|
| `runner.py` > 400-line cap (510 lines) | **Resolved** — v1 split in 1.2.0 (`sdk_loop_core.py`, `sdk_loop_session.py`) |
| Chrome Wayland drag-drop | **Carried forward** — see §2c above |
| Transcript [File N] chip rendering | **Needs verification** — see §2d above |
| `bearings status/log/pending` polish | **Carried forward** — see §2f above |
| Session Reorg slice 6 (LLM-assisted analyze) | **Not in v1 scope** — deferred per v0.17.x plan; no v1 tracking item exists |
| Plan-mode stale-pin bug (upstream Anthropic #53046) | **Upstream only** — mitigation (`plan-pin-rotate.py` hook) active in both versions |
| Flaky test `test_get_tool_calls_filters_by_message_ids` | **Needs check** — observed once in v0.17.x; unknown v1 status |
| CHANGELOG.md gaps for v0.3.x–v0.5.x | **N/A** — v1 has its own CHANGELOG from scratch |

---

## 5. Recommended actions (priority order)

1. **Update `bearings-parity-gaps.md`** — mark all 26 `[ ]` items as `[x]`,
   update completion table to 35/35. One commit.
2. **Update `bearings-gap-closure-pipeline.md`** — status → `✅ COMPLETE`.
3. **Recreate or strike `bearings-v1-rebuild.md`** — either locate and update
   it or replace its reference in CLAUDE.md with a pointer to the CHANGELOG.
4. **Verify [File N] chip rendering** (§2d) — open a session with attachments
   in the UI, confirm bubble renders chips not bare tokens.
5. **Check `test_get_tool_calls_filters_by_message_ids`** for flakiness in v1.
6. **Track SDK timeout root cause** (§2a) — no action needed until it recurs;
   structlog capture is now wired.
7. **SSH push fix** (§2e) — sysadmin `chown` from a real shell when convenient.

### v1.3.0 gap-closure resolution (2026-06-10)

Items above addressed by the following commits on v1-rebuild:

| Gap (§) | Commit | Summary |
|---|---|---|
| §2b `GET /api/usage/headroom` missing | `f7fb38cb` | add headroom alias route + tests + openapi regen |
| §2d `[File N]` chip rendering | `3a89d4a5` | renderUserBodyHtml() in MessageTurn.svelte |
| §2f `bearings pending list` CLI polish | `1361f23f` | wire pending add/resolve/list subcommands |
| release close-out | v1.3.0 release commit | pyproject 1.3.0, CHANGELOG, junk-file removal |
