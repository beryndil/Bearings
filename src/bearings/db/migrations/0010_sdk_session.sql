-- Persist the claude-agent-sdk session id so history resumes across
-- WebSocket reconnects. The SDK stamps `AssistantMessage.session_id`
-- on the first assistant reply; we capture it and pass it back as
-- `resume=...` on subsequent prompts so each fresh SDK client picks
-- up where the prior one left off instead of starting blind.

ALTER TABLE sessions ADD COLUMN sdk_session_id TEXT;
