# Bearings (v1 rebuild)

Localhost web UI that streams Claude Code agent sessions. This branch
(`v1-rebuild`) is the v0.18.0 rebuild; v0.17.x lives at
`/home/beryndil/Projects/Bearings/` and is **behavioral reference only**
past Phase 0.

## Authoritative documents

| Concern | Location |
|---|---|
| Strategic plan + 29-item build order | `~/.claude/plans/bearings-v1-rebuild.md` |
| Routing-feature spec | `docs/model-routing-v1-spec.md` |
| Operational coding directives | `~/.claude/coding-standards.md` |
| Deferred / orphaned work | `TODO.md` (this repo) |

When the routing spec and coding standards both apply: spec provides
*inputs* (numbers, dataclass shapes, endpoint surfaces, UI strings),
standards provides *containers* (config module, strict typing, validation
discipline, i18n-ready string tables). Audit checks both for routing
files; coding standards alone for everything else.

## Repo invariants

* Branch: `v1-rebuild` (orphan history). Pre-commit `branch-verifier`
  hook rejects commits to any other branch.
* Worktree: `/home/beryndil/Projects/Bearings-v1/`.
* SDK: `claude-agent-sdk~=0.1.69` (compatible-release pin).
* Python: ≥ 3.12. Type-checking: `mypy --strict`, no `Any`.
* Concurrent run vs v0.17.x: port **8788** (vs 8787),
  DB `~/.local/share/bearings-v1/` (vs `~/.local/share/bearings/`),
  systemd unit `bearings-v1.service` (vs `bearings.service`).

## First-time setup (per fresh checkout)

```bash
scripts/setup-worktree.sh   # idempotent — wires per-worktree hooks isolation + uv sync
```

Why a setup script: this worktree shares its parent `.git/` with the
v0.17.x main worktree. Without per-worktree `core.hooksPath` isolation,
installing pre-commit here would trample the v0.17.x hooks. The script
sets `extensions.worktreeConfig=true` on the shared `.git/config`, then
`core.hooksPath=$PWD/.githooks-v1` on this worktree only. The hook shim
under `.githooks-v1/` is checked in.

## Quality gates

```bash
uv sync --extra dev
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest -q
uv run pre-commit run --all-files
```

CI runs the same gates plus `systemd-analyze verify` on the unit and
`lychee` on every markdown file. See `.github/workflows/ci.yml`.

## Reference-read protocol (binding on every executor)

* Items 0.4 onward must NOT read any file under
  `/home/beryndil/Projects/Bearings/src/` or
  `/home/beryndil/Projects/Bearings/frontend/`.
* The auditor inspects the executor transcript for tool calls touching
  those paths. Any match → automatic GAPS regardless of output quality.
* Behavioral specs at `docs/behavior/<subsystem>.md` (added in item 0.3)
  are the only authoritative behavioral source past Phase 0.

## Item completion contract

* Self-verification block precedes every DONE / DONE_WITH_CONCERNS post.
  Format and rules: `~/.claude/plans/bearings-v1-rebuild.md`
  §"Self-verification".
* Status vocabulary: `DONE` · `DONE_WITH_CONCERNS` · `BLOCKED` (physical /
  reachability / credential walls only) · `HANDED_OFF → <new_id>`.
  `NEEDS_CONTEXT` is retired.
* Decision discipline: never ask "A or B?" on code calls — decide and
  move on per `~/.claude/rules/decision-discipline.md`.

## TODO.md discipline

`TODO.md` exists at repo root for orphaned / deferred work that is not
yet scheduled into a master-checklist item. Per the global directive,
append the moment work is deferred or an error is passed on. Scheduled
work belongs in the master checklist (id `0f6e4006fb1d4340bda9983af3432064`),
not in `TODO.md`.
