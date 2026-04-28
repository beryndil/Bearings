# Bearings (v1 rebuild)

Localhost web UI that streams Claude Code agent sessions. This branch
(`v1-rebuild`) is the v0.18.0 rebuild — orphan history, behavioral parity
with v0.17.x plus model-routing v1.

* **Plan:** `~/.claude/plans/bearings-v1-rebuild.md`
* **Spec:** [`docs/model-routing-v1-spec.md`](docs/model-routing-v1-spec.md)
* **Status:** scaffolding (item 0.1 of 29 — see plan §"Build order")

## Quickstart (post-bootstrap)

```bash
uv sync
uv run pytest -q
uv run bearings  # bootstrap notice (full CLI lands in item 1.7)
```

## Quality gates

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
pre-commit run --all-files
```

The full 12-tool stack (ruff, mypy, pytest, vulture, radon, interrogate,
codespell, pip-audit, eslint, prettier, svelte-check, knip, ts-prune,
depcheck, lychee) is wired through `.pre-commit-config.yaml` and CI.

## Concurrent run with v0.17.x

| | v0.17.x | v1 |
|---|---|---|
| Port | 8787 | 8788 |
| DB | `~/.local/share/bearings/` | `~/.local/share/bearings-v1/` |
| systemd unit | `bearings.service` | `bearings-v1.service` (this repo: `config/`) |
