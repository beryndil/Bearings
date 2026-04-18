# Twrminal — Open Tasks

## Scaffold reference

Full scaffold plan: `~/.claude/plans/here-are-the-architectural-ticklish-puppy.md`.
v0.1.1 slice plan: `~/.claude/plans/hazy-hatching-honey.md`.

## v0.1.1 — shipped

- [x] `AgentSession` wired to `claude-agent-sdk`.
- [x] WebSocket streaming in `src/twrminal/api/ws_agent.py`.
- [x] DB CRUD in `src/twrminal/db/store.py` (sessions + messages).
- [x] Real `/api/sessions` routes.
- [x] `api/models.py` Pydantic DTOs.
- [x] Lifespan wiring `init_db` → `app.state.db`.

## v0.1.2 — shipped

- [x] `GET /api/sessions/{id}/messages` history route.
- [x] `twrminal send` CLI subcommand.
- [x] `ToolCallEnd` event via `ToolResultBlock` translation.
- [x] Tool-call persistence (store CRUD + WS handler writes).

## v0.1.3 — shipped

- [x] Frontend three-panel shell wired end-to-end.
- [x] `api.ts` with `AgentEvent` union + CRUD helpers.
- [x] Svelte 5 stores for sessions + conversation + WS agent.
- [x] Markdown rendering (marked + typography plugin).
- [x] Browser-exercised: create session → WS connects → UI shows connected.

## v0.1.4 — next slice

- [ ] Syntax-highlight code blocks in conversation (integrate `shiki`;
  already in deps but unused).
- [ ] Dialog-free delete confirm: replace `confirm()` with an inline
  "are you sure" affordance so UI is scriptable.
- [ ] Show tool-call timing once finished (`startedAt` → elapsed even
  after end). Currently only "running" elapsed is meaningful.
- [ ] Persist selected session across reloads (localStorage).
- [ ] Auto-reconnect WS on disconnect; surface retry state in UI.
- [ ] Frontend unit tests (vitest + @testing-library/svelte).

## v0.1.5+

- [ ] Prometheus collectors for `/metrics` route (currently empty registry).
- [ ] `routes_history.py` — implement `/api/history/export` and
  `/api/history/daily/{date}`.
- [ ] CI frontend build artifact test — verify `npm run build` actually
  produces files under `src/twrminal/web/dist/`.
- [ ] Auth gate: enable `auth.enabled` path (currently no-op).
- [ ] Wire `message_id` on tool_calls rows (currently always NULL on
  insert; could be backfilled at `MessageComplete` time).

## Decisions pending

- [x] GitHub org for remote push: `Beryndil/Twrminal` (configured as
  `origin`).
- [ ] Partial-message semantics: confirm `include_partial_messages=True`
  emits token deltas as expected on first live agent run.
