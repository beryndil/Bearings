-- Tag primitives (v0.2.0): global tag registry + session_tags join.
-- Tags are orthogonal to projects (projects land in 0007). Pinned +
-- sort_order drive sidebar ordering (pinned first, then ascending
-- sort_order, then id) and, later in v0.2, tag-memory precedence.
-- Timestamps use TEXT ISO to match every other timestamp column in
-- the DB — the spec's INTEGER epoch was illustrative, not canonical.

CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT,
    pinned INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE session_tags (
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, tag_id)
);

CREATE INDEX idx_session_tags_tag ON session_tags(tag_id);
