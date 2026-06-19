"""``bearings serve`` subcommand — production entry point for the web UI.

Per ``docs/architecture-v1.md`` §1.1.1 the CLI is the only supported
boot path; per ``docs/behavior/bearings-cli.md`` §"bearings serve"
the subcommand wires :class:`Settings` → :func:`load_schema` →
:func:`create_app` → ``uvicorn.run``.

Per arch §1.1.1 the subcommand body stays thin: parsing args, opening
the DB connection (with schema applied), calling :func:`create_app`,
registering the shutdown hook, and handing off to ``uvicorn``. No
business logic — every observable behavior comes from
:mod:`bearings.web.app`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

import aiosqlite
import uvicorn

import bearings.web.routes.reply_actions as _reply_actions_mod
from bearings.agent.quota import QuotaPoller, build_noop_fetcher, build_real_fetcher
from bearings.agent.reply_transform import build_run_transform
from bearings.config.constants import CLAUDE_CODE_BINARY, CLI_EXIT_OK, DEFAULT_AVATARS_STORAGE_ROOT
from bearings.config.settings import Settings
from bearings.db.connection import ensure_severity_tags, load_schema
from bearings.web.app import create_app

_LOG = logging.getLogger(__name__)


def build_subparser(parent: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Wire the ``serve`` subcommand into ``parent``."""
    serve = parent.add_parser(
        "serve",
        help="Run the Bearings web UI on the configured host/port",
        description=(
            "Boot the FastAPI app from `bearings.config.settings.Settings` and serve "
            "it via uvicorn. The DB connection on `app.state.db_connection` opens "
            "during the FastAPI startup event and closes on shutdown."
        ),
    )
    serve.add_argument(
        "--host",
        default=None,
        help="bind host (defaults to Settings.host — '127.0.0.1' under loopback policy)",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=None,
        help="bind port (defaults to Settings.port — 8787 in v1)",
    )
    serve.add_argument(
        "--log-level",
        default="info",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        help="uvicorn log level (default: info)",
    )
    serve.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> int:
    """Hand off to uvicorn with the DB lifecycle hooks attached.

    Returns :data:`CLI_EXIT_OK` once uvicorn exits cleanly; any
    exception bubbles up as a non-zero exit per the CLI alphabet.

    The DB connection opens *synchronously before* :func:`create_app`
    so the runner factory is constructed with ``session_setup`` wired
    (`web/app.py:149`). Without this, ``create_app`` falls into the
    no-db branch, the factory ships with ``_session_setup=None``, and
    every posted prompt queues forever because no supervisor task is
    ever spawned. The shutdown hook stays in the FastAPI lifecycle so
    uvicorn closes the connection on graceful exit.
    """
    settings = Settings()
    db = asyncio.run(_connect_db(settings.db_path))

    # Wire the real quota fetcher when the Claude Code binary is present;
    # fall back to the noop fetcher (fail-open, both bucket pcts None) when
    # the binary is absent so the server still boots on machines where
    # Claude Code is not installed.  The noop fetcher is the explicit,
    # named fallback per spec §4 — NOT the default.
    if CLAUDE_CODE_BINARY.exists():
        fetcher = build_real_fetcher()
        _LOG.info("serve: quota poller using real fetcher (claude binary: %s)", CLAUDE_CODE_BINARY)
    else:
        fetcher = build_noop_fetcher()
        _LOG.warning(
            "serve: claude binary not found at %s; quota poller using noop fetcher "
            "(guard will fail-open — no downgrade decisions)",
            CLAUDE_CODE_BINARY,
        )

    # Wire the real LLM advisor callable for reply-action transformations.
    # The module-level ``run_transform`` in reply_actions defaults to
    # _stub_run_transform (raises NotImplementedError); we replace it here
    # at startup so production POST /api/sessions/{id}/reply_actions calls
    # the real Claude API.  Tests monkeypatch the module attribute directly
    # and are unaffected by this assignment.
    _reply_actions_mod.run_transform = build_run_transform()
    _LOG.info("serve: reply_actions.run_transform wired to real LLM callable")

    poller = QuotaPoller(connection=db, fetcher=fetcher)
    app = create_app(
        db_connection=db,
        quota_poller=poller,
        enable_driver_dispatch=True,
        billing_mode=settings.billing.mode,
        data_dir=settings.db_path.parent,
        avatars_root=DEFAULT_AVATARS_STORAGE_ROOT,
    )

    @app.on_event("shutdown")
    async def _close_db() -> None:
        live = getattr(app.state, "db_connection", None)
        if live is not None:
            await live.close()

    host = args.host if args.host is not None else settings.host
    port = args.port if args.port is not None else settings.port
    uvicorn.run(app, host=host, port=port, log_level=args.log_level)
    return CLI_EXIT_OK


async def _connect_db(db_path: Path) -> aiosqlite.Connection:
    """Open the long-lived sqlite connection before app construction.

    Calls :func:`load_schema` so that a fresh DB (e.g. first-time install)
    gets the DDL applied before :func:`create_app` runs. The schema is fully
    idempotent (``IF NOT EXISTS`` + ``INSERT OR IGNORE`` guards) so
    re-application against an existing DB is a no-op.

    Also calls :func:`ensure_severity_tags` so the five canonical severity
    tags (Blocker/Critical/Medium/Low/QoL) are present on every server boot.
    The call is idempotent — existing rows are never duplicated.
    """
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await load_schema(db)
    await ensure_severity_tags(db)
    return db


__all__ = ["build_subparser"]
