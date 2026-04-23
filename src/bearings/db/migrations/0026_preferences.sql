-- Server-side user preferences (v1). Single-row table (id=1 singleton)
-- backing the display name, the theme slot, and the server copies of
-- the three existing localStorage keys (model, working_dir, notify).
-- The auth token deliberately stays in localStorage — it's
-- client-side by design; the server can't authorize itself on its own
-- stored token.
--
-- Typed single-row over a generic key/value row shape because:
--   - Bearings is single-user; migration-per-field cost is cheap.
--   - Typed columns keep the Pydantic PATCH validator honest.
--   - Matches the existing schema aesthetic (sessions, messages, tags
--     are all typed rows, not key/value soup).
--
-- Column notes:
--   display_name        — nullable; NULL renders as the literal 'user'
--                         (the Anthropic API role) in MessageTurn.
--                         Pydantic caps length at 64 chars and
--                         coalesces empty / whitespace-only strings to
--                         NULL so accidental blank-name submits don't
--                         produce invisible role labels. No character
--                         restrictions beyond length — Svelte text
--                         interpolation auto-escapes so injection is
--                         not a risk.
--   theme               — nullable slot reserved for the themes
--                         session (plan slug `liberal-ocean-whisker`
--                         pending; plug 197df8d80e2c44d281452c2e89365679).
--                         NULL means "no theme preference set; render
--                         the server default." Values land when themes
--                         ships.
--   default_model       — nullable; seeded from the migrated
--                         localStorage key `bearings:defaultModel` on
--                         first successful GET if the server row is
--                         still at its seed state (updated_at matches
--                         seed timestamp, fields are NULL/default).
--   default_working_dir — nullable; same migration pattern, from
--                         `bearings:defaultWorkingDir`.
--   notify_on_complete  — INTEGER 0/1 (SQLite boolean convention).
--                         Default 0. Seeded from
--                         `bearings:notifyOnComplete`.
--   updated_at          — ISO-8601 UTC, set by application code on
--                         every successful PATCH. The auto-migrate
--                         detector keys on this field matching the
--                         seed timestamp to decide whether the
--                         one-shot localStorage migration should fire.
--                         If the PATCH fails on the migration path,
--                         localStorage stays intact and the detector
--                         retries on next boot (idempotent).
--
-- `CHECK (id = 1)` plus `INSERT OR IGNORE` makes this a singleton:
-- the GET/PATCH handlers never have to consider the
-- row-doesn't-exist case. Seed row is created at migration time so
-- the runner never ships a table that the API can't immediately
-- serve.

CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    display_name TEXT,
    theme TEXT,
    default_model TEXT,
    default_working_dir TEXT,
    notify_on_complete INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO preferences (id, updated_at)
    VALUES (1, datetime('now'));
