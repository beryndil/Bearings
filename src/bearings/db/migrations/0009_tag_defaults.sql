-- Tag-level defaults. Replaces the project-level defaults that
-- briefly lived on `projects` in 0007 (dropped in 0008). When a
-- session is being created and the user has selected one or more
-- tags, the UI pre-fills working_dir / model from the
-- highest-precedence tag's defaults.
--
-- Precedence matches tag-memory precedence: pinned DESC, sort_order
-- ASC, id ASC — last-in-list wins (later tags override earlier
-- tags' defaults).

ALTER TABLE tags ADD COLUMN default_working_dir TEXT;
ALTER TABLE tags ADD COLUMN default_model TEXT;
