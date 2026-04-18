# Twrminal

Localhost web UI for Claude Code agent sessions. FastAPI backend streams
session events over WebSocket to a SvelteKit frontend; SQLite persists
history across restarts.

## Status

Alpha — v0.1.0 scaffold. Route surface is wired; session, streaming, and
persistence implementations are stubbed.

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

The frontend build writes static assets into `src/twrminal/web/dist/`, which
FastAPI mounts at `/`.

## Run

```bash
uv run twrminal serve
# then open http://127.0.0.1:8787
```

Health probe:

```bash
curl -s http://127.0.0.1:8787/api/health
```

## Service install

```bash
install -Dm644 config/twrminal.service ~/.config/systemd/user/twrminal.service
systemctl --user daemon-reload
systemctl --user enable --now twrminal.service
```

## Config

`~/.config/twrminal/config.toml`. Defaults are baked in; override only the
keys you need.

| Section    | Key                  | Default                          | Purpose                          |
|------------|----------------------|----------------------------------|----------------------------------|
| `server`   | `host`               | `127.0.0.1`                      | Bind address                     |
| `server`   | `port`               | `8787`                           | Bind port                        |
| `auth`     | `enabled`            | `false`                          | Future token/key gate            |
| `agent`    | `working_dir`        | `~/`                             | CWD for agent sessions           |
| `agent`    | `model`              | `claude-opus-4-7`                | Default model                    |
| `storage`  | `db_path`            | `~/.local/share/twrminal/db.sqlite` | Persistence                 |
| `metrics`  | `enabled`            | `false`                          | Prometheus `/metrics` endpoint   |

## License

MIT. See `LICENSE`.
