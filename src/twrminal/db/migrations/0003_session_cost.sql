-- 0003_session_cost.sql: running total of SDK-reported cost in USD.
-- Sourced from ResultMessage.total_cost_usd at each assistant turn.

ALTER TABLE sessions ADD COLUMN total_cost_usd REAL NOT NULL DEFAULT 0;
