-- View-tracking columns on sessions (v0.7.x): carry two timestamps so
-- the sidebar can render a "finished but unviewed" indicator that's
-- distinct from the live green-ping "currently working" badge.
--
-- `last_completed_at`: stamped whenever the runner persists a
-- MessageComplete for the session. Reads the wall-clock at persist
-- time (shared with `updated_at`).
--
-- `last_viewed_at`: stamped by `POST /api/sessions/{id}/viewed` when
-- the user opens / focuses the session. Frontend fires on sidebar
-- select and on `visibilitychange` → visible while a session is
-- selected. Never written while the browser tab is hidden.
--
-- "Unviewed" is derived at render time:
--     last_completed_at IS NOT NULL
--     AND (last_viewed_at IS NULL OR last_completed_at > last_viewed_at)
--
-- Both columns are additive, nullable, no backfill — existing rows
-- stay NULL until the next complete / view.

ALTER TABLE sessions ADD COLUMN last_completed_at TEXT;
ALTER TABLE sessions ADD COLUMN last_viewed_at TEXT;
