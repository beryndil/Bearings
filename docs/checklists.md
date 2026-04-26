# Checklists

Checklists are first-class sessions in Bearings — alongside chat sessions, not
a feature inside one. A checklist session holds a structured tree of items
(with notes, nesting, and optional links to paired chat sessions) that you,
your collaborators, or an autonomous agent run can work through.

This doc is the canonical reference for what *"create a checklist"* means in
Bearings. When the wording is ambiguous, this doc wins.

## Why checklists are first-class

`~/.claude/coding-standards.md` §36 says:

> All non-trivial multi-step work tracked in a structured checklist. Each
> item must have verifiable completion criteria.

Bearings ships this as a session `kind` because:

- **Plain markdown TODOs lose state.** A long Claude conversation will
  eventually compact, summarize, or fork. A checklist living only in the
  chat scrollback comes out the other side with edits missing.
- **Chat conflates work with the trace of work.** A stable index of WHAT
  to do (the checklist) and a separate scrollback of HOW you did each item
  (the linked chat) keeps both clean.
- **Autonomous runs need a structured queue.** `auto_driver` walks
  checklist items, not chat messages. A markdown TODO cannot drive a run.

## Checklist vs LiveTodos vs cross-project TODO.md

Three surfaces, all named "todo" or "checklist" at some point. They coexist
deliberately:

| Surface | What it is | Lifetime | Who edits |
|---|---|---|---|
| **Checklist session** (this doc) | Persistent structured tree of items, optionally linked to chat sessions. | Forever, across restarts. | Human via UI; any client via REST. |
| **LiveTodos widget** | Sticky card mirroring the agent's in-conversation `TodoWrite` list. | Per-conversation, ephemeral. | Only the agent inside that conversation. |
| **Cross-project `TODO.md`** | Markdown at each project root, tracking deferred work as it happens. Surfaced by the `bearings todo` CLI. | Forever, in git. | Human + agent edits; lint enforced by `bearings todo check`. |

Use a **checklist session** when you need a structured work tracker that
outlives any single conversation.

## The two session kinds

Bearings sessions carry a `kind` discriminator:

- **`kind="chat"`** (default) — streaming Claude conversation. Has a
  *read-only* `GET /todos` mirroring the agent's `TodoWrite` calls.
- **`kind="checklist"`** — structured item tree. Has the writable
  `/checklist/items` API. Can spawn or link paired chat sessions per item.

If you `POST /api/sessions/{id}/checklist/items` against a chat-kind session
you get **400 "session is not a checklist session"** — the discriminator at
work. Chat sessions can only have their read-only `/todos` view, populated by
the agent inside the conversation, not by external API calls.

## §36 format mapping

The standards format from `~/.claude/coding-standards.md` §36:

```
- [ ] Item: short title
  - Context: spec / doc / what this is
  - Files: what gets created or modified
  - Done when: concrete completion criteria
  - Notes: optional dependencies / warnings
```

Bearings's `ItemCreate` schema accepts:

```json
{
  "label": "short title",
  "notes": "Context: … | Files: … | Done when: … | Notes: …",
  "parent_item_id": null,
  "sort_order": null
}
```

Convention: pack the §36 sub-fields into `notes` joined by ` | ` or newlines.
Use `parent_item_id` for the Item / sub-step nesting that §36 leaves
implicit. The picking-up agent reads `label` for what to do and `notes` for
how to verify.

## UI flow

1. **Create** — sidebar `📋 New checklist` (or `Ctrl+Shift+P → New
   checklist`). Pick at least one project tag and one severity tag.
2. **Add items** — input row at the top of the right pane. Enter creates a
   top-level item; Tab demotes (sets `parent_item_id`); Shift+Tab promotes.
3. **Edit notes** — click an item to expand. The notes editor accepts
   markdown.
4. **Check off** — click the checkbox (or `Space` while focused).
   Auto-cascade closes parents when all children are checked (v0.9).
5. **Pair with a chat** — right-click an item → *Open paired chat* spawns a
   new chat-kind session linked to this item. *Link to existing session*
   binds it to a chat you already have.
6. **Talk to Claude about the checklist itself** — the embedded
   `ChecklistChat` panel above the list body lets you discuss scope, ask
   for refinement, or have the agent split items. The prompt assembler
   injects the title, notes, and current item tree (with `[x]`/`[ ]`
   glyphs) into every turn so the agent stays grounded.
7. **Autonomous run (advanced)** — `▶︎ Run` walks items in order. The
   auto-driver opens each linked chat, drives it to its Done-when, marks
   the item checked, and moves on. Stop anytime; resume later.

## REST API

All paths relative to your bind (default `http://127.0.0.1:8787`). Live
schema at `GET /openapi.json`.

### Create a checklist session

```bash
curl -sS -X POST http://127.0.0.1:8787/api/sessions \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "[Roadmap] Q3 features",
    "working_dir": "/home/dave/Projects/Bearings",
    "model": "claude-opus-4-7",
    "tag_ids": [2, 9],
    "kind": "checklist",
    "description": "Top-level scope for Q3. Each item links to its design session."
  }'
```

Response carries the new session `id`.

### Add a top-level item

```bash
curl -sS -X POST http://127.0.0.1:8787/api/sessions/<sid>/checklist/items \
  -H 'Content-Type: application/json' \
  -d '{
    "label": "[Feature] Add CONTRIBUTING.md",
    "notes": "Files: CONTRIBUTING.md (new), README.md. Done when: doc covers setup/test/style and is linked from README."
  }'
```

Response carries the new item's integer `id`.

### Nest a step under it

```bash
curl -sS -X POST http://127.0.0.1:8787/api/sessions/<sid>/checklist/items \
  -H 'Content-Type: application/json' \
  -d '{
    "label": "Add Quality Gates section",
    "notes": "Content: ruff, mypy, pytest, npm check, npm test. Done when: all five commands listed and verified.",
    "parent_item_id": <parent_id>
  }'
```

### Link an item to an existing chat session

```bash
curl -sS -X POST http://127.0.0.1:8787/api/sessions/<sid>/checklist/items/<iid>/link \
  -H 'Content-Type: application/json' \
  -d '{"chat_session_id": "<chat_id>"}'
```

`chat_session_id` is nullable — pass `null` to detach.

### Toggle checked

```bash
curl -sS -X POST http://127.0.0.1:8787/api/sessions/<sid>/checklist/items/<iid>/toggle
```

Other endpoints worth knowing:

- `PATCH /checklist` — update the top-level notes block on the checklist.
- `PATCH /checklist/items/{iid}` — update an item's label or notes.
- `DELETE /checklist/items/{iid}`.
- `POST /checklist/reorder` — move items, including changing `parent_item_id`.
- `POST /checklist/items/{iid}/chat` — spawn a fresh paired chat
  (alternative to linking an existing one).
- `POST /checklist/run` / `GET /checklist/run` / `DELETE /checklist/run` —
  autonomous run controls.

## Worked example: a multi-fix audit tracker

When a code review or standards audit produces a list of bounded fixes,
this is the shape:

- N **chat-kind** sessions, one per fix, each carrying a self-contained
  plug (GOAL / WHY / STEPS / DO NOT / VERIFY / FILES).
- One **checklist-kind** master session indexing all N, with each
  top-level item linked back to its chat session and its steps nested as
  child items.

Recipe:

```python
import json, urllib.request

BASE = "http://127.0.0.1:8787"
PROJECT_TAG = 2          # Bearings
SEV_CRITICAL = 9
WD = "/home/dave/Projects/Bearings"
MODEL = "claude-opus-4-7"

def post(path, body):
    req = urllib.request.Request(
        BASE + path, method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))

# 1. Spawn one chat session per fix
chats = []
for fix in fixes:
    s = post("/api/sessions", {
        "title": f"[{fix.kind}] {fix.title}",
        "working_dir": WD, "model": MODEL,
        "tag_ids": [PROJECT_TAG, fix.severity_tag_id],
        "description": fix.plug,
    })
    chats.append(s["id"])

# 2. Spawn the master checklist
master = post("/api/sessions", {
    "title": "[Audit] Standards review followups",
    "working_dir": WD, "model": MODEL,
    "tag_ids": [PROJECT_TAG, SEV_CRITICAL],
    "kind": "checklist",
    "description": "Master tracker. Each item links to its dedicated chat.",
})

# 3. Add items, link them to their chat sessions, nest steps as children
for fix, chat_id in zip(fixes, chats):
    item = post(f"/api/sessions/{master['id']}/checklist/items", {
        "label": fix.title,
        "notes": f"Files: {fix.files}. Done when: {fix.done_when}.",
    })
    post(f"/api/sessions/{master['id']}/checklist/items/{item['id']}/link", {
        "chat_session_id": chat_id,
    })
    for step in fix.steps:
        post(f"/api/sessions/{master['id']}/checklist/items", {
            "label": step.label,
            "notes": step.notes,
            "parent_item_id": item["id"],
        })
```

## Best practices for writing items

**Label.** Imperative phrase, verb first. Skip the ticket prefix unless
severity is meaningful at a glance.

> Good: `Add Quality Gates section`<br>
> Less good: `Quality Gates`<br>
> Bad: `update contributing`

**Notes.** Always include `Done when:`. Always. §36 exists because "I think
this is done" is the most common failure mode.

> Good: `Files: src/bearings/server.py. Done when: forced raise inside any
> route returns sanitized 500 with no stack to client; full traceback still
> in log.`<br>
> Bad: `Add an exception handler.`

**Nesting.** Two levels max in practice — top-level area, child step.
Deeper trees become unreadable in the sidebar.

**Linking.** If the work needs more than one back-and-forth turn with
Claude, link to a paired chat session. If it's a one-line edit you can do
yourself in passing, leave it unlinked.

**Tag with severity.** Use the `severity` tag group (Blocker / Critical /
Medium / Low / Quality of Life). The sidebar groups by severity; an
untagged checklist falls into "No severity" and is harder to find.

## Source tree pointers

- API routes: `src/bearings/api/routes_checklists.py`
- Persistence: `src/bearings/db/_checklists.py`
- Autonomous run: `src/bearings/agent/auto_driver.py`,
  `src/bearings/agent/checklist_sentinels.py`
- Frontend: `frontend/src/lib/components/ChecklistView.svelte`,
  `ChecklistChat.svelte`
- Schema: `src/bearings/db/schema.sql` (search for `checklist_items`)
- Migrations: `src/bearings/db/migrations/` (v0.7 / v0.9 / v0.16 carry the
  checklist-table evolution)

## Related

- README → *Checklists, live todos, paired chats*
- `docs/menus-toml.md` — right-click action IDs that target items
  (`item.toggle`, `item.open_paired_chat`, `item.link_to_session`, etc.)
- `~/.claude/coding-standards.md` §36 — the format spec this implements
- `~/.claude/CLAUDE.md` — Beryndil global discipline, including the
  cross-project `TODO.md` rule that complements (not replaces) checklist
  sessions
