# Bearings v0.17.x → v1 Feature Parity Audit
Date: 2026-06-19
Auditor: automated cross-read of source files (no archive src/ reads past this scope)

## Summary

~75 feature areas audited across backend routes, frontend components, DB schema,
WebSocket events, and behavioral flows.
**6 regressions (MISSING or DEGRADED).**
~40 equivalent.
~30 improved or new in v1.

---

## REGRESSIONS (Missing or Degraded in v1)

### R-1: `GET /api/sessions/running` and `GET /api/sessions/awaiting` — MISSING

**v0.17.x behavior:**
`routes_sessions.py` exposed two poll endpoints:
- `GET /api/sessions/running` → list of session ids whose runner has a turn in flight
- `GET /api/sessions/awaiting` → list of session ids parked on a permission decision or checklist-item `blocked_at`

Both were used as poll fallback when the `/ws/sessions` broadcast was down, driving the sidebar's "running" and "red-flashing" indicators.

**v1 status:**
Neither endpoint exists. The `diag.py` runner endpoint (`GET /api/diag/sessions`) returns runner state but in a completely different shape not consumable by the sidebar. The runner state arrives only over `runner_state` WS frames; there is no REST fallback poll.

**Risk:** When the WebSocket `/ws/sessions` is not connected (reconnect window), the sidebar cannot determine which sessions are running or awaiting. The amber/red indicator will be stale until WS reconnects.

**Files:**
- v0.17.x: `src/bearings/api/routes_sessions.py:155–205`
- v1: no equivalent; nearest is `src/bearings/web/routes/diag.py` (different shape, not wired to sidebar)

---

### R-2: `POST /sessions/{id}/reorg/analyze` — MISSING

**v0.17.x behavior:**
`routes_reorg.py:388` provided a read-only heuristic + optional LLM-backed analysis of a session's conversation, suggesting where to split or what to extract. Used by the ReorgPicker flow to offer AI-guided suggestions before committing a reorg.

**v1 status:**
The v1 `reorg.py` has merge, split (fork), move-message, list-audits, and undo-audit — but no `/analyze` endpoint. The `ReorgPicker.svelte` and `ReorgProposalEditor.svelte` components existed in v0.17.x wired to this analyze endpoint; v1's reorg is manual-only.

**Files:**
- v0.17.x: `src/bearings/api/routes_reorg.py:384–480`
- v0.17.x: `frontend/src/lib/components/ReorgPicker.svelte`, `ReorgProposalEditor.svelte`
- v1: `src/bearings/web/routes/reorg.py` (5 endpoints, no analyze)

---

### R-3: `GET /api/pending` (list pending operations) — MISSING

**v0.17.x behavior:**
`routes_pending.py:68` had `GET /api/pending` returning `list[PendingOperation]` — a structured list of every entry in `pending.toml`. The frontend `PendingOpsCard.svelte` / `PendingOpsBadge.svelte` called this on mount and on reconnect.

**v1 status:**
The v1 `pending.py` has only `POST /api/pending/{name}/resolve` and `DELETE /api/pending/{name}`. There is no list endpoint. Instead the v1 frontend reads `pending.toml` indirectly via `GET /api/fs/read?path=<abs_path>` and parses the raw TOML client-side (`pendingOps.ts`). This is functional but requires the frontend to know the working directory and to be able to reach the FS allow-root — it degrades silently to an empty list on permission mismatches instead of surfacing an error.

**Files:**
- v0.17.x: `src/bearings/api/routes_pending.py:68–78`
- v1: `src/bearings/web/routes/pending.py` (resolve + delete only); `frontend/src/lib/api/pendingOps.ts` (FS-read path)

---

### R-4: `POST /api/shell/open` → replaced by `POST /api/shell/exec` (behavioral change, DEGRADED)

**v0.17.x behavior:**
`routes_shell.py:116` had `POST /api/shell/open` — spawned a GUI process (terminal emulator, editor, file manager) configured in `config.toml` via `shell.terminal` / `shell.editor` / `shell.file_explorer` template keys. Fire-and-forget (`start_new_session=True`); 204 on spawn, 400 when unconfigured. Three context-menu actions wired to it: `link.open_in.editor`, `attachment.open_in.editor`, `attachment.open_in.file_explorer`.

**v1 status:**
`shell.py` has `POST /api/shell/exec` — executes an argv list and returns stdout/stderr (blocking). The fire-and-forget spawn-a-GUI pattern is gone. The v1 context-menu registry still registers `MENU_ACTION_LINK_OPEN_IN_EDITOR`, `MENU_ACTION_ATTACHMENT_OPEN_IN_EDITOR`, `MENU_ACTION_ATTACHMENT_OPEN_IN_FILE_EXPLORER` — these fire against the exec endpoint, but exec blocks until the process exits, which for a GUI app means the request hangs. The behavior of these context-menu entries is therefore broken in v1 for GUI targets (editor, file manager). CLI tools (e.g. `code -g path`) work correctly since they return quickly.

**Files:**
- v0.17.x: `src/bearings/api/routes_shell.py:116`
- v1: `src/bearings/web/routes/shell.py:44` — exec only

---

### R-5: Tag memory model changed — v0.17.x 1:1 (one `content` blob per tag) vs v1 N:M (multiple memories per tag with `title`, `body`, `enabled`) — SCHEMA BREAK on migration

**v0.17.x schema:**
```sql
CREATE TABLE IF NOT EXISTS tag_memories (
    tag_id INTEGER PRIMARY KEY REFERENCES tags(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```
One row per tag. The `content` column is a single markdown blob.

**v1 schema:**
```sql
CREATE TABLE IF NOT EXISTS tag_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);
```
Multiple rows per tag. Each has a `title` and `body` column; the old `content` field becomes `body`. No migration is provided in the v1 source that converts existing `tag_memories` rows from the v0.17.x shape to the v1 shape.

**Impact:** The v1 migration script (`scripts/migrate_v0_17_to_v0_18.py`) must handle the schema reshape. If existing memory content is not migrated, users lose all authored per-tag memories on upgrade.

**Files:**
- v0.17.x: `src/bearings/db/schema.sql:156–160`
- v1: `src/bearings/db/schema.sql:261–273`
- Migration: `scripts/migrate_v0_17_to_v0_18.py` (verify content/body rename is handled)

---

### R-6: `GET /api/sessions/{id}/tokens` — DEGRADED (field shape changes)

**v0.17.x behavior:**
`routes_sessions.py:468` returned `TokenTotalsOut` aggregating `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens` from `messages`.

**v1 status:**
`sessions_assembly.py:217` still has `GET /api/sessions/{session_id}/tokens`. However v1's messages table has a fundamentally different column layout (split into `executor_input_tokens`, `executor_output_tokens`, `advisor_input_tokens`, `advisor_output_tokens` plus legacy `input_tokens`, `output_tokens`). The `TokenTotalsOut` response model must correctly aggregate across both legacy and new columns. The risk is that the total displayed in the Inspector metrics tab is wrong for mixed (pre-migration + post-migration) sessions if the aggregation only reads the new columns.

**Files:**
- v1: `src/bearings/web/routes/sessions_assembly.py:217`; `src/bearings/db/messages.py` (verify aggregation)

---

## EQUIVALENT (Same behavior in v1)

The following features exist in both versions with the same observable behavior:

**Backend routes:**
- `POST/GET/PATCH/DELETE /api/sessions` — session CRUD
- `POST /api/sessions/{id}/close`, `/reopen`, `/viewed`
- `POST /api/sessions/{id}/prompt`
- `GET /api/sessions/{id}/messages`, `/tool_calls`, `/todos`, `/system_prompt`
- `GET/POST/DELETE /api/sessions/{id}/tags/{tag_id}`
- `POST /api/sessions/bulk` — bulk operations
- `GET/POST/DELETE /api/tags` with `/memory` (single-memory model in v0.17.x, equivalent GET in v1)
- `POST/GET/DELETE /api/checkpoints` + `/{id}/fork`
- `GET/POST/DELETE /api/templates` + `/{id}/instantiate`
- `POST/GET/DELETE /api/vault` — vault browsing
- `GET/PATCH /api/preferences` + `/avatar` CRUD
- `POST /api/sessions/{id}/spawn_from_reply/{msg_id}`
- `POST /api/sessions/{id}/spawn_classify` — sensitive data classification
- `GET /api/commands`
- `GET /api/health`, `GET /api/version`
- `GET /metrics`
- `POST /api/uploads`, batch upload
- `GET /api/fs/list`, `GET /api/fs/read`, `POST /api/fs/pick`
- `GET /api/history/search`
- `GET /api/history/export`
- Session import/export (`/import`, `/{id}/export`)
- `GET /api/sessions/{id}/work_evidence`
- `GET /api/reply_actions/catalog`, `POST /api/sessions/{id}/reply_actions/{action_id}`
- `POST/GET /api/sessions/{id}/reorg/merge`, `/split`, `/move`, `/audits`, undo-audit
- `GET /api/ui-config`
- `POST /api/sessions/{id}/preview_title` (was `suggest_title` in v0.17.x)

**WebSocket events (per-session `/ws/sessions/{id}`):**
All event types are equivalent between v0.17.x and v1:
- `user_message`, `token`, `thinking`, `tool_call_start`, `tool_call_end`, `tool_output_delta`, `tool_progress`
- `message_start`, `message_complete`, `context_usage`, `error`, `turn_replayed`
- `approval_request`, `approval_resolved`, `todo_write_update`
- `runner_status` (status snapshot frame)

**WebSocket broadcast (`/ws/sessions`):**
Both versions broadcast: `session_upsert`, `session_delete`, `runner_state`, `tag_upsert`, `tag_delete`.

**Frontend pages:**
- `/` (main session list), `/sessions/[id]` (conversation view)
- `/vault`, `/analytics`, `/memories`, `/tags`, `/settings`

**Frontend components:**
- Approval modal, AskUserQuestion modal, context menu system, conversation/MessageTurn, VirtualItem virtualization, CheckpointGutter, SessionEdit, TagEdit, FeedbackButton, BackendStatusBanner, AuthGate, Inspector (tabs: Context, Files, Changes, Metrics)

**Context menu actions:**
All v0.17.x action IDs are present in v1 (`session.*`, `message.*`, `tag.*`, `tag_chip.*`, `tool_call.*`, `code_block.*`, `link.*`, `checkpoint.*`, `multi_select.*`, `attachment.*`, `pending_operation.*`).

---

## IMPROVED (v1 is better)

1. **Session list pagination** — v1 `GET /api/sessions` returns `SessionsPage` with `limit`/`offset` and tag filter split into `tag_ids_project`, `tag_ids_severity`, `tag_ids_other`. v0.17.x returned an unbounded list.

2. **Tag classification** — v1 adds `'project'` class (was `'general'` only in v0.17.x besides `'severity'`). Tags with class `'project'` drive sidebar grouping; `≤1 per session` cardinality is API-enforced.

3. **Model routing system** — v1 adds `tag_routing_rules`, `system_routing_rules`, `quota_snapshots` tables and a full routing/quota API surface (`/api/routing/tag-rules`, `/api/routing/system-rules`, `/api/quota`). Completely absent in v0.17.x.

4. **Analytics** — v1 has 13 analytics endpoints (usage breakdowns by model, per-tag, per-turn, plus plug-block FTS index). v0.17.x had only one (`GET /api/analytics/summary`).

5. **Diag endpoints** — v1 adds `GET /api/diag/server`, `/diag/sessions`, `/diag/drivers`, `/diag/quota`. v0.17.x had none.

6. **Paired chats audit table** — v1 `paired_chats` table logs every autonomous-driver leg spawn with `leg_number`, `spawned_by`, `closed_at`. v0.17.x had no per-leg audit trail.

7. **Auto driver runs** — v1 `auto_driver_runs` replaces v0.17.x's `auto_run_state`. v1 adds `'paused'` state, `items_blocked`, `items_attempted` counters, `outcome`/`outcome_reason`, `failure_policy`, `visit_existing`. More granular lifecycle.

8. **Session fields** — v1 adds `closing_summary`, `routing_advisor_model`, `routing_advisor_max_uses`, `routing_effort_level`, `pivot_message_id`, `parent_session_id`, `template_id`, `message_count`, `last_context_pct/tokens/max`. v0.17.x lacked these.

9. **Messages table** — v1 adds per-model routing columns (`executor_model`, `advisor_model`, `effort_level`, `routing_source`, `routing_reason`, `matched_rule_id`, `evaluated_rules`, `executor_input/output_tokens`, `advisor_input/output_tokens`) and a `stopped` flag. v0.17.x had only flat `input_tokens`/`output_tokens`.

10. **SDK session entries** — v1 persists SDK JSONL transcript lines in `sdk_session_entries` table for full conversation-context restoration on supervisor respawn. v0.17.x used an in-process `sdk_session_id` pointer only.

11. **Vault** — v1 vault is DB-backed (indexed, searchable by `vault_id` or `by-path`). v0.17.x vault scanned filesystem on every request.

12. **Templates** — v1 templates have `description`, `advisor_model`, `advisor_max_uses`, `effort_level`, `permission_profile`. v0.17.x templates had `body` (system prompt), `working_dir`, `model`, `session_instructions`, `tag_ids_json` only.

13. **Inspector tabs** — v1 adds `InspectorRouting`, `InspectorUsage`, `InspectorAgent`, `InspectorInstructions` tabs. v0.17.x had `ChangesTab`, `ContextTab`, `FilesTab`, `MetricsTab`.

14. **Shell exec** — v1 `POST /api/shell/exec` returns stdout/stderr, useful for scripted invocations. v0.17.x `POST /api/shell/open` was fire-and-forget GUI-spawn only (see also R-4).

15. **Pending operations** — v1 reads `pending.toml` raw via `GET /api/fs/read` + client-side TOML parser, removing a server-side TOML dependency and giving the frontend a richer structured view with `command` and `dir` fields that the v0.17.x `PendingOperation` model did not carry.

16. **Import endpoint** — v1 has `POST /api/import/bearings` (DB-to-DB migration from v0.17.x), not present in v0.17.x.

17. **Tag memories** — v1 supports multiple memories per tag with individual `title`, `body`, `enabled` toggling. v0.17.x was 1:1 (single `content` blob per tag).

18. **Sessions broadcast heartbeat** — v1 `SessionsBroadcaster` sends `{"kind":"heartbeat","ts":<float>}` frames on idle, keeping the WS connection alive through idle timeouts. v0.17.x had no heartbeat on the sessions broadcast channel.

19. **WS overflow policy** — v1 `SessionsBroadcaster` uses a bounded subscriber queue with explicit `on_overflow` callback that schedules `websocket.close(4000)`. v0.17.x used an unbounded queue.

---

## DB Schema Deltas

### Tables present in v0.17.x and changed in v1 (breaking changes)

| Table | v0.17.x | v1 | Impact |
|---|---|---|---|
| `sessions` | `sdk_session_id TEXT` column present | Column dropped; replaced by `sdk_session_entries` table | v0.17.x data in `sdk_session_id` is not migrated by default |
| `sessions` | No `closing_summary`, `routing_*`, `pivot_message_id`, `parent_session_id`, `template_id`, `message_count`, `last_context_*` columns | All added | Additive; safe |
| `tags` | `tag_group` column, values: `('general', 'severity')` | `class` column, values: `('project', 'severity', 'general')` | **Column rename**: migration must handle `tag_group` → `class` |
| `tags` | No `working_dir` column | `working_dir TEXT` added | Additive |
| `tags` | No `updated_at` column | `updated_at TEXT NOT NULL` added | Migration must supply default |
| `tag_memories` | `tag_id INTEGER PRIMARY KEY`, `content TEXT` — one blob per tag | `id AUTOINCREMENT`, `tag_id`, `title`, `body`, `enabled` — multiple per tag | **Schema reshape**: `content` → `body`; `title` field new; migration must convert rows or lose content |
| `messages` | `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `pinned`, `hidden_from_context`, `replay_attempted_at`, `thinking TEXT` | Routing columns added; `thinking` dropped from messages (moved to SDK session entries); `stopped` added; `replay_attempted_at` dropped | `thinking` column drop is a schema break — v0.17.x stored extended thinking text there |
| `reorg_audits` (v0.17.x) | `id`, `source_session_id`, `target_session_id`, `target_title_snapshot`, `message_count`, `op` (move/split/merge), `created_at` | `reorg_audit` (renamed), `id TEXT PK`, `dst_session_id`, `src_session_id`, `merged_at`, `src_title`, `boundary_msg_id`, `kind` (merge-only) | **Table rename + shape change**: v0.17.x tracked move/split/merge; v1 `reorg_audit` tracks merge only (split creates a new session, audited differently). Migration must handle rename. |
| `session_templates` (v0.17.x) | `id TEXT PK`, `name`, `body`, `working_dir`, `model`, `session_instructions`, `tag_ids_json` (IDs) | `templates` (renamed), `id INTEGER AUTOINCREMENT`, `name`, `description`, `model`, `advisor_model`, `advisor_max_uses`, `effort_level`, `permission_profile`, `system_prompt_baseline`, `working_dir_default`, `tag_names_json` (names, not IDs) | **Table rename + tag reference change** (IDs → names); `body` → `system_prompt_baseline` rename |
| `checklist_items` | `blocked_at` column present (migration 0033) | `blocked_at`, `blocked_reason_category`, `blocked_reason_text` present | v1 adds two reason columns — additive |
| `auto_run_state` (v0.17.x) | `state` = `('running', 'finished', 'errored')` — no `paused` | `auto_driver_runs` (renamed), `state` = `('idle', 'running', 'paused', 'finished', 'errored')` | **Table rename + new states** |

### Tables in v0.17.x with NO v1 equivalent

None — every v0.17.x table has a v1 counterpart (though sometimes renamed).

### Tables in v1 with NO v0.17.x equivalent (new)

- `sdk_session_entries` — SDK JSONL transcript persistence
- `vault` — DB-backed plan/TODO index
- `paired_chats` — per-leg autonomous driver audit
- `auto_driver_runs` — replaces `auto_run_state` (new columns)
- `tag_routing_rules` — per-tag model routing
- `system_routing_rules` — global model routing fallback
- `quota_snapshots` — rolling /usage poll cache
- `turns` — per-turn token accounting (analytics)
- `plug_blocks` + `plug_blocks_fts` — context-plug content store + FTS index
- `session_plug_blocks` — session↔plug mapping
- `bucket_snapshots` — /usage poll raw archive
- `suppressed_warnings` — dismissed plug-length warnings

---

## WebSocket Event Deltas

### Events in v0.17.x NOT present in v1 — NONE

All v0.17.x agent-stream event types are present in v1:
`user_message`, `token`, `thinking`, `tool_call_start`, `tool_call_end`, `tool_output_delta`, `tool_progress`, `message_start`, `message_complete`, `context_usage`, `error`, `turn_replayed`, `approval_request`, `approval_resolved`, `todo_write_update`, `runner_status` (ping equivalent), `ping`/heartbeat.

### Events in v1 NOT present in v0.17.x (new)

- `routing_badge` — carries the routing decision (executor model, advisor model, effort) alongside `message_complete` so the Inspector routing tab can display it without a REST round-trip.
- `turn_stopped` — emitted when a turn is interrupted via Stop; drives the `[stopped]` chip on the assistant bubble.

### Broadcast channel (`/ws/sessions`) — EQUIVALENT

Both versions broadcast `session_upsert`, `session_delete`, `runner_state`, `tag_upsert`, `tag_delete`. v1 adds heartbeat frames on idle; v0.17.x did not.
