-- Bearings v1 — canonical SQLite schema.
--
-- This is the single source of truth for the on-disk database layout. The
-- bootstrap module in `src/bearings/db/connection.py` reads this file once
-- per process and applies it via `executescript`, idempotent on re-init
-- because every table uses `IF NOT EXISTS` and every seeded row uses
-- `INSERT OR IGNORE` against a partial unique index.
--
-- Authoritative references:
--   • docs/architecture-v1.md §1.1.3, §4 (table inventory, dataclass
--     shapes that the routing/quota columns must mirror).
--   • docs/model-routing-v1-spec.md §3 (tag_routing_rules,
--     system_routing_rules, default rule seed table), §5 (per-message
--     routing/usage columns), §4 + §8 + §9 (quota_snapshots).
--   • docs/behavior/chat.md (sessions kind discriminator: chat-kind
--     sessions, paired-chat back-pointer, header executor model).
--   • docs/behavior/checklists.md (checklist_items tree shape, sort_order,
--     blocked_at + blocked_reason_*, paired-chat sentinel statuses).
--   • docs/behavior/paired-chats.md (1:1 leaf↔chat link plus per-leg
--     audit rows from the autonomous driver).
--   • docs/behavior/vault.md (read-only plan / TODO index — kind,
--     mtime, size, slug, optional title).
--
-- Conventions:
--   • Every CREATE TABLE uses explicit column types and explicit NULL /
--     NOT NULL discipline.
--   • Every FOREIGN KEY carries an ON DELETE clause.
--   • Indexes are explicitly named `idx_<table>_<columns>`; no auto names.
--   • Timestamps are TEXT ISO-8601 (UTC, with offset) for the user-facing
--     session/message/checklist tables, matching the existing orchestrator
--     surface that downstream items integrate with. The routing-spec
--     surfaces (tag_routing_rules, system_routing_rules, quota_snapshots)
--     use INTEGER unix seconds verbatim per spec §3 and §4 — this is the
--     authoritative source for those tables and the rebuild does not
--     diverge.

-- ---------------------------------------------------------------------------
-- sessions — every conversation surface in the sidebar.
--
-- The `kind` discriminator (per docs/architecture-v1.md §1 and
-- docs/behavior/chat.md / docs/behavior/checklists.md) splits chat-kind
-- sessions (runnable, have a composer + transcript) from checklist-kind
-- sessions (no composer; render a structured-list pane). The CHECK
-- constraint pins the v1 vocabulary; future kinds amend the CHECK.
--
-- `checklist_item_id` is the chat-side back-pointer for a paired chat
-- (the inverse of `checklist_items.chat_session_id`); see
-- docs/behavior/paired-chats.md.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id                       TEXT    PRIMARY KEY,
    kind                     TEXT    NOT NULL CHECK (kind IN ('chat', 'checklist')),
    title                    TEXT    NOT NULL,
    description              TEXT,
    session_instructions     TEXT,
    working_dir              TEXT    NOT NULL,
    model                    TEXT    NOT NULL,
    permission_mode          TEXT,
    max_budget_usd           REAL,
    total_cost_usd           REAL    NOT NULL DEFAULT 0,
    message_count            INTEGER NOT NULL DEFAULT 0,
    last_context_pct         REAL,
    last_context_tokens      INTEGER,
    last_context_max         INTEGER,
    pinned                   INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),
    error_pending            INTEGER NOT NULL DEFAULT 0 CHECK (error_pending IN (0, 1)),
    checklist_item_id        INTEGER,
    created_at               TEXT    NOT NULL,
    updated_at               TEXT    NOT NULL,
    last_viewed_at           TEXT,
    last_completed_at        TEXT,
    closed_at                TEXT,
    FOREIGN KEY (checklist_item_id) REFERENCES checklist_items(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_kind_updated_at
    ON sessions(kind, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_closed_at
    ON sessions(closed_at) WHERE closed_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sessions_checklist_item_id
    ON sessions(checklist_item_id) WHERE checklist_item_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- messages — assistant + user + tool-result rows for chat-kind sessions.
--
-- Per docs/model-routing-v1-spec.md §5 and docs/architecture-v1.md §4.7,
-- every assistant turn carries per-model usage and routing-decision
-- columns from day 1 (no ALTER chain). The legacy flat
-- `input_tokens`/`output_tokens` pair is kept as nullable carriers for
-- migrated pre-routing data (`routing_source = 'unknown_legacy'`) per
-- spec §5 "Backfill for legacy data".
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id                       TEXT    PRIMARY KEY,
    session_id               TEXT    NOT NULL,
    role                     TEXT    NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content                  TEXT    NOT NULL,
    created_at               TEXT    NOT NULL,
    -- spec §5 routing-decision columns
    executor_model           TEXT,
    advisor_model            TEXT,
    effort_level             TEXT,
    routing_source           TEXT,
    routing_reason           TEXT,
    -- spec §5 per-model usage columns (from ResultMessage.model_usage)
    executor_input_tokens    INTEGER,
    executor_output_tokens   INTEGER,
    advisor_input_tokens     INTEGER,
    advisor_output_tokens    INTEGER,
    advisor_calls_count      INTEGER DEFAULT 0,
    cache_read_tokens        INTEGER,
    -- legacy flat columns (kept nullable for pre-routing-aware migrated rows
    -- per spec §5 "Backfill for legacy data" and arch §4.7 Optional[int]).
    input_tokens             INTEGER,
    output_tokens            INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id_created_at
    ON messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_routing_source
    ON messages(routing_source) WHERE routing_source IS NOT NULL;

-- ---------------------------------------------------------------------------
-- tags — top-level categorisation. Every chat or checklist session must
-- carry ≥1 tag (enforced at the API boundary, not at the schema level —
-- the schema permits zero rows in session_tags so a half-built create
-- transaction can roll back cleanly).
--
-- `default_model` and `working_dir` are the inheritance fields described
-- in docs/behavior/chat.md ("the chat inherits the checklist's working
-- directory, model, and tags") and docs/behavior/checklists.md
-- ("inherits the checklist's working directory, model, and tags").
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tags (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    name                     TEXT    NOT NULL UNIQUE,
    color                    TEXT,
    default_model            TEXT,
    working_dir              TEXT,
    created_at               TEXT    NOT NULL,
    updated_at               TEXT    NOT NULL
);

-- session_tags — many-to-many between sessions and tags.
CREATE TABLE IF NOT EXISTS session_tags (
    session_id               TEXT    NOT NULL,
    tag_id                   INTEGER NOT NULL,
    created_at               TEXT    NOT NULL,
    PRIMARY KEY (session_id, tag_id),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)     REFERENCES tags(id)     ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_session_tags_tag_id
    ON session_tags(tag_id);

-- ---------------------------------------------------------------------------
-- tag_memories — system-prompt fragments attached to tags.
-- Per docs/behavior/chat.md and docs/architecture-v1.md §1.1.3, these
-- are the "tag memories as system-prompt fragments" surface that the
-- prompt assembler reads per turn.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tag_memories (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id                   INTEGER NOT NULL,
    title                    TEXT    NOT NULL,
    body                     TEXT    NOT NULL,
    enabled                  INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at               TEXT    NOT NULL,
    updated_at               TEXT    NOT NULL,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tag_memories_tag_id_enabled
    ON tag_memories(tag_id, enabled);

-- ---------------------------------------------------------------------------
-- vault — read-only filesystem index of plan markdown + project TODO files.
-- Per docs/behavior/vault.md the vault surfaces two kinds:
--   • Plans — `.md` directly under each configured plan root.
--   • Todos — `TODO.md` matched by configured globs.
-- Both kinds carry: absolute path, slug (basename minus extension),
-- optional title (first `# heading`), mtime, size. The list is bucketed
-- by kind, sorted newest-first within each bucket.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vault (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    path                     TEXT    NOT NULL UNIQUE,
    slug                     TEXT    NOT NULL,
    title                    TEXT,
    kind                     TEXT    NOT NULL CHECK (kind IN ('plan', 'todo')),
    mtime                    INTEGER NOT NULL,
    size                     INTEGER NOT NULL,
    last_indexed_at          INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vault_kind_mtime
    ON vault(kind, mtime DESC);

-- ---------------------------------------------------------------------------
-- checklist_items — tree of work items under a checklist-kind session.
--
-- Schema mirrors the live orchestrator-side API surface that
-- downstream items 1.6 / 1.7 must integrate with. Per
-- docs/behavior/checklists.md:
--   • parent_item_id is a self-FK for the nested-item tree.
--   • sort_order is per-parent (root items use parent_item_id IS NULL).
--   • chat_session_id is the leaf↔chat pair pointer (per
--     docs/behavior/paired-chats.md leaves only — schema-level
--     enforcement of "leaves only" lives in the API layer).
--   • blocked_at + blocked_reason_category + blocked_reason_text are
--     the sentinel-blocked surface (item-status amber).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS checklist_items (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    checklist_id             TEXT    NOT NULL,
    parent_item_id           INTEGER,
    label                    TEXT    NOT NULL,
    notes                    TEXT,
    sort_order               INTEGER NOT NULL DEFAULT 0,
    checked_at               TEXT,
    chat_session_id          TEXT,
    blocked_at               TEXT,
    blocked_reason_category  TEXT,
    blocked_reason_text      TEXT,
    created_at               TEXT    NOT NULL,
    updated_at               TEXT    NOT NULL,
    FOREIGN KEY (checklist_id)    REFERENCES sessions(id)         ON DELETE CASCADE,
    FOREIGN KEY (parent_item_id)  REFERENCES checklist_items(id)  ON DELETE CASCADE,
    FOREIGN KEY (chat_session_id) REFERENCES sessions(id)         ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_checklist_items_checklist_id_sort_order
    ON checklist_items(checklist_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_checklist_items_parent_item_id_sort_order
    ON checklist_items(parent_item_id, sort_order)
    WHERE parent_item_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_checklist_items_chat_session_id
    ON checklist_items(chat_session_id) WHERE chat_session_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- paired_chats — per-leg audit log of chat sessions paired to a leaf
-- checklist item.
--
-- The single live link is `checklist_items.chat_session_id`; this table
-- records the lineage of legs spawned by the autonomous driver per
-- docs/behavior/checklists.md ("the driver kills the current paired
-- chat's runner, spawns a successor leg…") and
-- docs/behavior/paired-chats.md ("successive chat rows for the same
-- item appear and close as the driver hands off legs"). UNIQUE on
-- (checklist_item_id, leg_number) so a re-run of the same leg dispatch
-- is rejected at the boundary.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paired_chats (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    checklist_item_id        INTEGER NOT NULL,
    chat_session_id          TEXT    NOT NULL,
    leg_number               INTEGER NOT NULL DEFAULT 1,
    spawned_by               TEXT    NOT NULL CHECK (spawned_by IN ('user', 'driver')),
    created_at               TEXT    NOT NULL,
    closed_at                TEXT,
    UNIQUE (checklist_item_id, leg_number),
    FOREIGN KEY (checklist_item_id) REFERENCES checklist_items(id) ON DELETE CASCADE,
    FOREIGN KEY (chat_session_id)   REFERENCES sessions(id)        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_paired_chats_chat_session_id
    ON paired_chats(chat_session_id);

-- ---------------------------------------------------------------------------
-- tag_routing_rules — per-tag routing rules, evaluated in priority order
-- before system_routing_rules. Schema verbatim from
-- docs/model-routing-v1-spec.md §3.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tag_routing_rules (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id                   INTEGER NOT NULL,
    priority                 INTEGER NOT NULL DEFAULT 100,
    enabled                  INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    match_type               TEXT    NOT NULL CHECK (match_type IN ('keyword', 'regex', 'length_gt', 'length_lt', 'always')),
    match_value              TEXT,
    executor_model           TEXT    NOT NULL,
    advisor_model            TEXT,
    advisor_max_uses         INTEGER DEFAULT 5,
    effort_level             TEXT    DEFAULT 'auto',
    reason                   TEXT    NOT NULL,
    created_at               INTEGER NOT NULL,
    updated_at               INTEGER NOT NULL,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tag_routing_rules_tag_id_priority_enabled
    ON tag_routing_rules(tag_id, priority, enabled);

-- ---------------------------------------------------------------------------
-- system_routing_rules — global fallback rules, evaluated when no tag
-- rule matches. Schema verbatim from docs/model-routing-v1-spec.md §3.
--
-- The seven rows seeded below match the §3 default table verbatim.
-- The partial unique index on (priority) WHERE seeded = 1 makes
-- INSERT OR IGNORE idempotent: re-running the bootstrap on an existing
-- DB silently skips the seven seeded rows without affecting any
-- user-added (seeded = 0) rule that happens to share a priority.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_routing_rules (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    priority                 INTEGER NOT NULL DEFAULT 1000,
    enabled                  INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    match_type               TEXT    NOT NULL CHECK (match_type IN ('keyword', 'regex', 'length_gt', 'length_lt', 'always')),
    match_value              TEXT,
    executor_model           TEXT    NOT NULL,
    advisor_model            TEXT,
    advisor_max_uses         INTEGER DEFAULT 5,
    effort_level             TEXT    DEFAULT 'auto',
    reason                   TEXT    NOT NULL,
    seeded                   INTEGER NOT NULL DEFAULT 0 CHECK (seeded IN (0, 1)),
    created_at               INTEGER NOT NULL,
    updated_at               INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_system_routing_rules_priority_enabled
    ON system_routing_rules(priority, enabled);
CREATE UNIQUE INDEX IF NOT EXISTS idx_system_routing_rules_seeded_priority
    ON system_routing_rules(priority) WHERE seeded = 1;

-- ---------------------------------------------------------------------------
-- quota_snapshots — rolling cache of /usage poll results.
-- Schema verbatim from docs/model-routing-v1-spec.md §4.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quota_snapshots (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at              INTEGER NOT NULL,
    overall_used_pct         REAL,
    sonnet_used_pct          REAL,
    overall_resets_at        INTEGER,
    sonnet_resets_at         INTEGER,
    raw_payload              TEXT
);

CREATE INDEX IF NOT EXISTS idx_quota_snapshots_captured_at
    ON quota_snapshots(captured_at DESC);

-- ---------------------------------------------------------------------------
-- Default system_routing_rules seed.
--
-- Verbatim from docs/model-routing-v1-spec.md §3 default rule table.
-- Seven rows, sparse priorities, sorted lowest-priority-number first
-- (= checked first). `INSERT OR IGNORE` against the partial unique
-- index `idx_system_routing_rules_seeded_priority` makes this idempotent
-- on re-init.
--
-- advisor_max_uses values follow spec §2 default policy:
--   Sonnet executor + Opus advisor → 5
--   Haiku executor + Opus advisor → 3
--   Opus executor (no advisor) → 0 (ignored when advisor_model IS NULL,
--     per docs/architecture-v1.md §4.1 RoutingDecision contract).
--
-- created_at / updated_at use strftime('%s', 'now') because the spec
-- §3 schema declares both columns as INTEGER NOT NULL — a fixed sentinel
-- (e.g. 0) would lie about when the seed landed; the strftime call
-- captures the wall-clock time of the first successful INSERT, and the
-- partial unique index prevents subsequent re-runs from re-stamping.
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO system_routing_rules (
    priority, enabled, match_type, match_value,
    executor_model, advisor_model, advisor_max_uses, effort_level,
    reason, seeded, created_at, updated_at
) VALUES (
    10, 1, 'keyword',
    'architect, design system, refactor across, multi-file, system design, plan mode, plan.md',
    'opus', NULL, 0, 'xhigh',
    'Hard architectural reasoning — Opus solo with extended thinking',
    1, strftime('%s', 'now'), strftime('%s', 'now')
);

INSERT OR IGNORE INTO system_routing_rules (
    priority, enabled, match_type, match_value,
    executor_model, advisor_model, advisor_max_uses, effort_level,
    reason, seeded, created_at, updated_at
) VALUES (
    20, 1, 'keyword',
    'rename, format, lint, typo, fix indent, capitalize, sort imports, remove unused, add comment',
    'haiku', 'opus', 3, 'low',
    'Mechanical task — Haiku handles 90% of Sonnet quality at fraction of cost',
    1, strftime('%s', 'now'), strftime('%s', 'now')
);

INSERT OR IGNORE INTO system_routing_rules (
    priority, enabled, match_type, match_value,
    executor_model, advisor_model, advisor_max_uses, effort_level,
    reason, seeded, created_at, updated_at
) VALUES (
    30, 1, 'keyword',
    'explore, find where, search the, map out, list all, locate',
    'haiku', 'opus', 3, 'low',
    'Exploration — Haiku is what Anthropic auto-selects for the Explore subagent',
    1, strftime('%s', 'now'), strftime('%s', 'now')
);

INSERT OR IGNORE INTO system_routing_rules (
    priority, enabled, match_type, match_value,
    executor_model, advisor_model, advisor_max_uses, effort_level,
    reason, seeded, created_at, updated_at
) VALUES (
    40, 1, 'regex',
    '^(what|where|when|who|how do I) ',
    'haiku', 'opus', 3, 'low',
    'Quick lookup',
    1, strftime('%s', 'now'), strftime('%s', 'now')
);

INSERT OR IGNORE INTO system_routing_rules (
    priority, enabled, match_type, match_value,
    executor_model, advisor_model, advisor_max_uses, effort_level,
    reason, seeded, created_at, updated_at
) VALUES (
    50, 1, 'length_lt', '80',
    'haiku', 'opus', 3, 'low',
    'Short query, simple task',
    1, strftime('%s', 'now'), strftime('%s', 'now')
);

INSERT OR IGNORE INTO system_routing_rules (
    priority, enabled, match_type, match_value,
    executor_model, advisor_model, advisor_max_uses, effort_level,
    reason, seeded, created_at, updated_at
) VALUES (
    60, 1, 'length_gt', '4000',
    'sonnet', 'opus', 5, 'high',
    'Long context, complex problem',
    1, strftime('%s', 'now'), strftime('%s', 'now')
);

INSERT OR IGNORE INTO system_routing_rules (
    priority, enabled, match_type, match_value,
    executor_model, advisor_model, advisor_max_uses, effort_level,
    reason, seeded, created_at, updated_at
) VALUES (
    1000, 1, 'always', NULL,
    'sonnet', 'opus', 5, 'auto',
    'Workhorse default',
    1, strftime('%s', 'now'), strftime('%s', 'now')
);
