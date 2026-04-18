# Twrminal — Open Tasks

## Scaffold reference

Full scaffold plan: `~/.claude/plans/here-are-the-architectural-ticklish-puppy.md`.
Source of truth until the stubs are replaced with real implementations.

## v0.1.0 — stubs to implement

- [ ] `AgentSession` (`src/twrminal/agent/session.py`) — wire to
  `claude-agent-sdk`; stream events into the WS channel.
- [ ] WebSocket streaming (`src/twrminal/api/ws_agent.py`) — bridge
  `AgentSession` event stream to connected browser clients.
- [ ] DB query layer (`src/twrminal/db/store.py`) — move beyond
  `init_db`; add session/message/tool-call CRUD.
- [ ] Frontend three-panel shell (`frontend/src/routes/+page.svelte`) —
  replace placeholder with real session list / conversation / inspector.
- [ ] Prometheus collectors for `/metrics` route.
- [ ] CI frontend build artifact test — ensure `npm run build` produces
  expected files.

## Decisions pending

- [ ] GitHub org for remote push: Beryndil vs Dev-VulX.
