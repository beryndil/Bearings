-- Slice 1 of the Checklist Sessions plan
-- (`~/.claude/plans/nimble-checking-heron.md`). Adds a second session
-- kind (`'checklist'`) that renders a structured item list instead of
-- a conversation.
--
-- Deliberately NOT overloading `messages`: checklist rows carry fields
-- (`checked_at`, `sort_order`, `parent_item_id`) that don't fit the
-- message shape, and `messages` participates in reorg / SDK priming /
-- token accounting — none of which apply to checklists. Separate
-- tables keep every existing chat-scoped query untouched.
--
-- Additive and safe: the `kind` column is NOT NULL DEFAULT 'chat', so
-- every existing session backfills as a chat. The two new tables are
-- empty until the checklist API lands (Slice 2). Frontend doesn't read
-- the column until Slice 3.

ALTER TABLE sessions ADD COLUMN kind TEXT NOT NULL DEFAULT 'chat'
    CHECK (kind IN ('chat', 'checklist'));

-- One checklist per session (1:1). PK == session_id so the
-- cascade-on-delete on the session row sweeps the checklist away
-- automatically; no orphan cleanup needed.
CREATE TABLE checklists (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    -- Optional longform body rendered above the item list. Same role
    -- as `sessions.description` but checklist-scoped so editing notes
    -- doesn't touch the sidebar-visible description column.
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Checklist items. `sort_order` is user-controlled via drag-reorder.
-- `parent_item_id` enables nested items in a later slice; the column
-- ships now so nesting doesn't need a second migration — it stays
-- NULL on every top-level row until the UI grows a nesting affordance.
CREATE TABLE checklist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checklist_id TEXT NOT NULL REFERENCES checklists(session_id) ON DELETE CASCADE,
    parent_item_id INTEGER REFERENCES checklist_items(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    notes TEXT,
    -- NULL = unchecked. Non-null ISO timestamp = when the user checked
    -- the box. Storing the timestamp rather than a bool means we can
    -- later show "checked 3h ago" without a second column.
    checked_at TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_checklist_items_checklist
    ON checklist_items(checklist_id, sort_order);
CREATE INDEX idx_checklist_items_parent
    ON checklist_items(parent_item_id);
