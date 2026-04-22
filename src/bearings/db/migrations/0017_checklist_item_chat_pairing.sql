-- Slice 4 of the Checklist Sessions plan
-- (`~/.claude/plans/nimble-checking-heron.md`). Adds symmetric nullable
-- FK columns so a checklist item can be "worked on" in a paired chat
-- session. Click an item → a chat opens about that item; the prompt
-- assembler injects the checklist context layer on every turn so the
-- agent knows what it's addressing.
--
-- Both columns are nullable and ON DELETE SET NULL — a deleted
-- checklist doesn't destroy the chat history (chat degrades to a
-- plain session with a "(checklist deleted)" breadcrumb), and a
-- deleted chat doesn't strand the checklist (item simply reverts to
-- "no chat opened yet" state).
--
-- Additive and safe: every existing row defaults to NULL on both
-- sides. Frontend doesn't read either column until the ChecklistView
-- "💬 Work on this" affordance lands in the same version.

ALTER TABLE checklist_items
    ADD COLUMN chat_session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL;

ALTER TABLE sessions
    ADD COLUMN checklist_item_id INTEGER REFERENCES checklist_items(id) ON DELETE SET NULL;

-- Point lookups on either side of the pairing are cheap and common:
-- ChecklistView queries items-with-pairing in one SELECT, and the
-- prompt assembler reverse-looks-up the item from the session id on
-- every turn build.
CREATE INDEX idx_checklist_items_chat_session
    ON checklist_items(chat_session_id);
CREATE INDEX idx_sessions_checklist_item
    ON sessions(checklist_item_id);
