-- Checkpoints (Phase 7 of docs/context-menu-plan.md). A checkpoint
-- is a named anchor at a specific `message_id` inside a session, so
-- the user can fork from "just before that big refactor prompt" or
-- "after the agent settled the API design". The fork path re-enters
-- the existing `import_session` shape — plan §4.2 calls this out so
-- we don't rebuild the message-id remap wheel.
--
-- Column shape per plan §4.2:
--   id TEXT PK          — uuid4 hex, stable across renames
--   session_id TEXT NN  — owning session; cascade-delete when the
--                         session is removed
--   message_id TEXT     — the exact message the checkpoint anchors
--                         at; nullable so a dropped-message audit
--                         (reorg) doesn't orphan the checkpoint row
--   label TEXT          — user-visible name; nullable so an untitled
--                         checkpoint ("just auto-checkpoint before
--                         my risky prompt") is legal
--   created_at TEXT NN  — ISO-8601, UTC
--
-- Index on (session_id, created_at) so the gutter-chip query
-- ("every checkpoint for this session, newest first") is O(log N)
-- instead of a full scan. Created_at beats id for ordering because
-- the id is a random uuid — no lexical order property.

CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    message_id TEXT,
    label TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_session_created
    ON checkpoints(session_id, created_at);
