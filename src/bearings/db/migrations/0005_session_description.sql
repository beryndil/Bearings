-- Add a free-form description column to sessions.
-- Nullable — existing rows default to NULL and render as "no description".
-- Intended for short context notes (what the session is *for*) that live
-- alongside the title; the title stays short for sidebar rendering, the
-- description can run multiple lines and is edited in the SessionEdit modal.

ALTER TABLE sessions ADD COLUMN description TEXT;
