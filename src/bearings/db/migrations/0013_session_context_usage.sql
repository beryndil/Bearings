-- Cache the most recent ContextUsageResponse snapshot on the session
-- row so a fresh browser load / reconnect has a context-pressure
-- number to render before the next `message_complete` fires. The live
-- ContextUsage WS event is still the source of truth for the currently
-- rendered session — this column only backs the first paint after
-- reconnect + the session-list badge.
--
-- All three columns are optional (NULL on rows that predate this
-- migration, and NULL on sessions that haven't produced an assistant
-- turn yet). The percentage is stored as a float 0..100 for direct
-- display; total and max are stored as absolute token counts so the
-- frontend can render "45k / 200k" without another round-trip.
ALTER TABLE sessions ADD COLUMN last_context_pct REAL;
ALTER TABLE sessions ADD COLUMN last_context_tokens INTEGER;
ALTER TABLE sessions ADD COLUMN last_context_max INTEGER;
