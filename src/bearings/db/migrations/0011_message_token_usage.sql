-- Per-turn token accounting from ResultMessage.usage, for subscription
-- users whose bill is quota-denominated rather than dollar-denominated.
-- PAYG users keep reading sessions.total_cost_usd as before; these
-- columns are additive so nothing breaks for that path.
--
-- Nullable on purpose — historical rows stay NULL because per-turn
-- usage dicts were never recorded and can't be reconstructed. New
-- assistant turns written after this migration populate all four.

ALTER TABLE messages ADD COLUMN input_tokens INTEGER;
ALTER TABLE messages ADD COLUMN output_tokens INTEGER;
ALTER TABLE messages ADD COLUMN cache_read_tokens INTEGER;
ALTER TABLE messages ADD COLUMN cache_creation_tokens INTEGER;
