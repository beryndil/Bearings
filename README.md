# Bearings

Localhost web UI for Claude Code agent sessions. FastAPI backend streams
session events over WebSocket to a SvelteKit frontend; SQLite persists
history across restarts.

## Permission profiles

Bearings exposes Claude Code's full agent surface — file system access,
tool use, MCP servers, hooks. That posture is appropriate for a
single-operator workstation and dangerous on a shared box. Pick a
profile at install time so the gates start in the right position:

```bash
bearings init --profile safe          # locked-down public default
bearings init --profile workstation   # auth on, $HOME working_dir
bearings init --profile power-user    # today's permissive defaults
```

| gate                          | `safe`                        | `workstation`            | `power-user`           |
|-------------------------------|-------------------------------|--------------------------|------------------------|
| auth token                    | required, auto-generated      | required, auto-generated | off (loopback only)    |
| default `working_dir`         | `~/.local/share/bearings/workspaces/<id>` (sandbox) | `$HOME` | `$HOME` |
| `~/.claude/` settings inherit | none                          | full                     | full                   |
| MCP servers inherit           | no                            | yes                      | yes                    |
| hook scripts inherit          | no                            | yes                      | yes                    |
| `bypassPermissions` mode      | blocked                       | allowed (ephemeral)      | allowed                |
| fs picker root                | workspace sandbox             | `$HOME`                  | `$HOME`                |
| commands palette              | project `.claude/` only       | + user `~/.claude/`      | + plugin marketplaces  |
| per-session budget cap        | $5 default                    | uncapped                 | uncapped               |
| runner idle TTL               | 60 s                          | 15 min                   | 15 min                 |

Every gate is also an independent config knob — pick a profile, then
edit individual lines in `~/.config/bearings/config.toml` for
mix-and-match. The active profile name + every gate state are printed
on every `bearings serve` startup so the operator sees their posture
at a glance. `profile.show_banner = false` opts out for
systemd-user operators who already read the journal.

## Status

Alpha — `0.3.x` development. Permission-profile preset layer landed
in v0.4 (sibling to the 2026-04-21 security-audit ship-blockers).
v0.1 is feature-complete and closed out at v0.1.40. v0.2 adds tags
as the single organizational primitive with per-tag markdown memories
injected into the system prompt, per-tag defaults for `working_dir`
/ `model`, and a mandatory ≥1-tag rule on every new session.
Spec: `V0.2.0_SPEC.md`.

## Features

### Streaming Claude agent sessions

Token deltas, thinking blocks, tool-call start/end, message-complete
cost. Run via `claude-agent-sdk`; pipe over WebSocket to the frontend.

### Tags, tag memories, tag defaults (v0.2)

- **Tags** — global, named, pinned or unpinned, with a `sort_order`.
  Many-to-many with sessions. Attach at create time or through the
  session edit modal.
- **Tag memories** — short markdown per tag, injected into the system
  prompt whenever the tag is on a session. Edited in the TagEdit
  modal (hover-reveal ✎ on each sidebar tag row). Precedence
  follows sidebar sort order — **the tag lower in the sort wins**
  when memories conflict. `tag_memories` table, `ON DELETE CASCADE`
  keyed to the tag.
- **Tag defaults** — optional `default_working_dir` and
  `default_model` per tag. The new-session form pre-fills from the
  highest-precedence attached tag. Pin a `bearings` tag with
  `default_working_dir = ~/Projects/Bearings` and it behaves like a
  "project" in any tool that has them.
- **Every session has ≥1 tag.** The new-session form gates on this;
  the API rejects `tag_ids: []` with a 400.
- **Layered system prompt** — base → tag memories (sort order) →
  session instructions. Inspectable in the Inspector Context tab
  with per-layer content + approximate token counts via
  `GET /api/sessions/{id}/system_prompt`.

### Session lifecycle

Session CRUD, rename, delete, JSON import/export (single + bulk
drag-drop), Enter-to-send / Shift+Enter newline, Stop button (SDK
`interrupt()`), ⌘/Ctrl+K sidebar search with match highlighting,
`?` cheat-sheet modal, message pagination. Per-session
`max_budget_usd` cap enforced via `ClaudeAgentOptions`; running total
cost stored on the session and rendered with amber/rose pressure
coloring at ≥80% / ≥100%. Per-session `session_instructions`
override edited inline in the Inspector Context tab — always the
last-wins layer.

### Infrastructure

- Opt-in bearer-token auth (`auth.token`) across REST + WS + CLI +
  frontend AuthGate modal; 401/4401 flips the store back to `invalid`.
- Prometheus `/metrics` (sessions, messages, tool calls, WS events,
  active connections) + JSON history export/daily/search routes.
- CLI subcommands: `bearings serve | init [--profile NAME] | send`.
  `init --profile {safe|workstation|power-user}` materializes the
  preset into `config.toml` and prints the active gate audit. `send`
  supports `--format=pretty` for human-readable output and `--token`
  for authenticated servers.

## Upgrading from v0.1

v0.2 migrations (`0006_tag_primitives.sql` through
`0009_tag_defaults.sql`) are additive except for v0.2.9's projects
teardown. Existing v0.1 sessions survive untouched *except* that
v0.2.9 wiped the sessions table — this was deliberate, done before
v0.2 had any production data. A fresh v0.2 install will auto-apply
every migration in sequence.

New sessions require ≥1 tag going forward. Existing tag-less
sessions (if any were restored from a v0.1 export after v0.2.0
shipped) are still readable but can't be created that way anymore
via the HTTP API.

## Requirements

- Python ≥ 3.11 (3.12 recommended via `.python-version`)
- Node ≥ 20
- [uv](https://docs.astral.sh/uv/)
- Claude Code authenticated locally (for the agent SDK to find credentials)

## Install

```bash
uv sync
cd frontend && npm install && npm run build
```

The frontend build writes static assets into `src/bearings/web/dist/`, which
FastAPI mounts at `/`.

## Run

```bash
uv run bearings serve
# then open http://127.0.0.1:8787
```

Health probe:

```bash
curl -s http://127.0.0.1:8787/api/health
```

## Service install

```bash
install -Dm644 config/bearings.service ~/.config/systemd/user/bearings.service
systemctl --user daemon-reload
systemctl --user enable --now bearings.service
```

## Config

`~/.config/bearings/config.toml`. Defaults are baked in; override only the
keys you need.

| Section    | Key                          | Default                          | Purpose                                              |
|------------|------------------------------|----------------------------------|------------------------------------------------------|
| `profile`  | `name`                       | *(unset)*                        | Active permission profile (info only — set by `init`)|
| `profile`  | `show_banner`                | `true`                           | Print gate audit on `serve` startup                  |
| `server`   | `host`                       | `127.0.0.1`                      | Bind address                                         |
| `server`   | `port`                       | `8787`                           | Bind port                                            |
| `auth`     | `enabled`                    | `false`                          | Gate REST + WS behind bearer                         |
| `auth`     | `token`                      | *(unset)*                        | Shared secret when `enabled`                         |
| `agent`    | `working_dir`                | `~/`                             | Legacy default cwd when `workspace_root` unset       |
| `agent`    | `workspace_root`             | *(unset)*                        | Per-session sandbox parent (sets `safe` posture)     |
| `agent`    | `model`                      | `claude-opus-4-7`                | Default model                                        |
| `agent`    | `default_max_budget_usd`     | *(unset)*                        | Per-session spend cap when caller doesn't pass one   |
| `agent`    | `allow_bypass_permissions`   | `true`                           | Allow header selector to escalate to `bypassPermissions` |
| `agent`    | `setting_sources`            | *(unset)*                        | SDK settings inheritance — `[]` = none, `null` = SDK default |
| `agent`    | `inherit_mcp_servers`        | `true`                           | Pass through `~/.claude/` MCP server registrations   |
| `agent`    | `inherit_hooks`              | `true`                           | Pass through `~/.claude/` hook scripts               |
| `commands` | `scope`                      | `"all"`                          | Slash-command palette scope (`all` / `user` / `project`) |
| `fs`       | `allow_root`                 | `~/`                             | `/api/fs/list` clamp                                 |
| `runner`   | `idle_ttl_seconds`           | `900`                            | Idle runner reaper threshold                         |
| `storage`  | `db_path`                    | `~/.local/share/bearings/db.sqlite` | Persistence                                       |
| `metrics`  | `enabled`                    | `false`                          | Prometheus `/metrics` endpoint                       |

## License

MIT. See `LICENSE`.
