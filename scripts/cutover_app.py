"""Boot the v1 FastAPI app pointed at a pre-existing v1 DB.

This script is the runtime half of the item 3.4 cutover smoke. The
companion script :mod:`cutover_smoke` invokes ``cutover_app`` as a
subprocess so its uvicorn loop runs in an isolated process tree —
that keeps the smoke harness's HTTP probes free of FastAPI lifecycle
state and means a hung worker can be torn down by signalling the
child PID rather than wrestling an asyncio loop.

Distinct from :mod:`scripts.e2e_server`: that script seeds a fresh
fixture DB before booting; this script expects the DB at ``--db`` to
already carry v1 schema + data (the typical input is the output of
``scripts/migrate_v0_17_to_v0_18.py``). No seeding, no debug router,
no /_e2e/* surface — just the production app pointed at user data.

Hermeticity:

* Binds 127.0.0.1 only (configurable port).
* The vault is materialised under ``--vault-root`` (an empty staging
  dir managed by the orchestrator); the production
  ``~/.claude/plans/`` and ``~/Projects/**/TODO.md`` paths are NOT
  read so the smoke is reproducible across hosts.
* The runner factory is the in-process variant (no Claude SDK
  subprocesses; the cutover smoke does not exercise streaming).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Final

import aiosqlite
import uvicorn
from fastapi import FastAPI

from bearings.config.settings import FsCfg, VaultCfg
from bearings.web.app import create_app
from bearings.web.runner_factory import build_in_process_factory

# +1 from the e2e harness port (8789) so a stray e2e_server does not
# collide with a parallel cutover smoke run.
CUTOVER_DEFAULT_PORT: Final[int] = 8790
CUTOVER_HOST: Final[str] = "127.0.0.1"

# Subdirectory names inside ``--vault-root``; mirror the directory
# layout :mod:`scripts.e2e_server` uses so the same shape of empty
# vault works against the v1 vault routes (which expect a plan root
# and a TODO glob even when both resolve to zero matches).
VAULT_PLAN_DIRNAME: Final[str] = "plans"
VAULT_PROJECTS_DIRNAME: Final[str] = "projects"
VAULT_TODO_GLOB_TEMPLATE: Final[str] = "{root}/projects/**/TODO.md"

EXIT_SUCCESS: Final[int] = 0
EXIT_DB_MISSING: Final[int] = 2

LOG: Final[logging.Logger] = logging.getLogger("bearings.cutover_app")


def _make_lifespan(
    db_path: Path,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Build a FastAPI lifespan that opens the long-lived DB connection.

    Mirrors the lifespan in :mod:`scripts.e2e_server` so the v1 app
    layer sees the same wiring it does under the e2e harness — the
    only difference is that no seeding runs before the connection is
    handed to ``app.state``.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        connection = await aiosqlite.connect(db_path)
        await connection.execute("PRAGMA foreign_keys = ON")
        app.state.db_connection = connection
        try:
            yield
        finally:
            await connection.close()

    return lifespan


def _materialise_empty_vault(root: Path) -> VaultCfg:
    """Create the empty plan + TODO directories and return a matching cfg.

    The directories are created (mkdir parents) but no files are
    written; the v1 vault routes return empty list responses, which is
    exactly what the smoke harness's probe expects. Tests for the
    actual vault surface live under :mod:`tests.test_vault_*` — this
    booter only proves the route plumbing wires up against the
    migrated DB.
    """
    plan_root = root / VAULT_PLAN_DIRNAME
    plan_root.mkdir(parents=True, exist_ok=True)
    projects_root = root / VAULT_PROJECTS_DIRNAME
    projects_root.mkdir(parents=True, exist_ok=True)
    todo_glob = VAULT_TODO_GLOB_TEMPLATE.format(root=root)
    return VaultCfg(plan_roots=(plan_root,), todo_globs=(todo_glob,))


def _build_app(db_path: Path, vault_root: Path) -> FastAPI:
    """Build the FastAPI app with the migrated DB + empty vault wired in.

    The DB is opened lazily via the lifespan so a misconfigured path
    surfaces as a uvicorn startup error (visible in the orchestrator's
    captured stderr) rather than a silent partial-boot. This is a
    sync function — the path resolution does not need an event loop,
    and ASYNC240 (sync ``Path`` calls in async funcs) flags an
    ``async def`` here as a lint error.
    """
    vault_cfg = _materialise_empty_vault(vault_root)
    # Allow the smoke harness's fs probe to read inside the vault root
    # without opening up arbitrary host paths. The orchestrator probes
    # ``GET /api/fs/list?path=<vault_root>`` to confirm the fs route
    # plumbing wires up against the in-process FsCfg; tests for the
    # actual fs surface live under :mod:`tests.test_fs_api`.
    fs_cfg = FsCfg(allow_roots=(vault_root.resolve(),))
    app = create_app(
        runner_factory=build_in_process_factory(),
        vault_cfg=vault_cfg,
        fs_cfg=fs_cfg,
    )
    app.router.lifespan_context = _make_lifespan(db_path)
    return app


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cutover_app",
        description=(
            "Boot the Bearings v1 FastAPI app pointed at a pre-migrated "
            "v1 DB. Used by scripts/cutover_smoke.py to exercise the "
            "migration's output through the v1 stack."
        ),
    )
    parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="Path to the v1 SQLite DB (typically the output of the migration script).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=CUTOVER_DEFAULT_PORT,
        help=f"TCP port to bind on 127.0.0.1 (default: {CUTOVER_DEFAULT_PORT}).",
    )
    parser.add_argument(
        "--vault-root",
        type=Path,
        required=True,
        help=(
            "Path to an empty staging directory the script populates with "
            "plans/ and projects/ subdirectories so the vault routes wire "
            "up against an empty (but well-formed) vault."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns the process exit code."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    if not args.db.exists():
        sys.stderr.write(f"[cutover_app] DB not found: {args.db}\n")
        return EXIT_DB_MISSING
    args.vault_root.mkdir(parents=True, exist_ok=True)
    sys.stderr.write(f"[cutover_app] db={args.db} port={args.port} vault_root={args.vault_root}\n")
    app = _build_app(args.db, args.vault_root)
    logging.basicConfig(level=logging.WARNING)
    config = uvicorn.Config(
        app,
        host=CUTOVER_HOST,
        port=args.port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()
    return EXIT_SUCCESS


if __name__ == "__main__":  # pragma: no cover — argv plumbing
    sys.exit(main())
