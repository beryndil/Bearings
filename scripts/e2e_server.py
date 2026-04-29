"""E2E test server — boots the FastAPI app + dist/ on a deterministic port.

Per master item 3.1, the Playwright suite needs a hermetic server it
can drive against the committed ``src/bearings/web/dist/`` bundle. The
production CLI's ``bearings serve`` is deferred (item-1.10+ scope);
this script is the test-only equivalent and is invoked from
``frontend/playwright.config.ts`` via ``webServer.command``.

What this script does, in order:

1. Parse ``--port``, ``--db``, ``--vault-root`` from CLI / env.
2. Materialise a temp DB (``schema.sql`` applied) and seed a small,
   deterministic dataset that every spec walks: tags, sessions
   (chat + checklist), tag memories, paired-chat link, vault docs,
   tag routing rules.
3. Build the FastAPI app via :func:`bearings.web.app.create_app` with
   the seeded DB connection, a :class:`VaultCfg` pointed at the temp
   vault root, a static :class:`QuotaPoller` that returns a
   deterministic snapshot, and an ``extra_routers=[debug_router]``
   that exposes ``/_e2e/*`` endpoints for event injection from
   Playwright.
4. Boot uvicorn on ``127.0.0.1:<port>`` and block until SIGINT /
   SIGTERM.

The script is the *only* legitimate consumer of the ``extra_routers``
seam on :func:`create_app`; production callers always pass ``None``.

Hermeticity: the script binds loopback, uses a fresh temp dir per
invocation, never reads ``~/.config/bearings/`` or
``~/.local/share/bearings/``, and never spawns a Claude SDK
subprocess. The runner placeholder from item 1.2 supplies the
in-memory ring buffer; debug-router event injection is what tests
use to drive streaming flows.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

import aiosqlite
import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from bearings.agent.events import (
    AgentEvent,
    MessageComplete,
    MessageStart,
    Token,
    ToolCallEnd,
    ToolCallStart,
    ToolOutputDelta,
)
from bearings.agent.quota import (
    QuotaSnapshot,
    record_snapshot,
)
from bearings.agent.runner import RunnerFactory
from bearings.config.constants import (
    SESSION_KIND_CHAT,
    SESSION_KIND_CHECKLIST,
)
from bearings.config.settings import VaultCfg
from bearings.db import (
    checklists as checklists_db,
)
from bearings.db import (
    memories as memories_db,
)
from bearings.db import (
    messages as messages_db,
)
from bearings.db import (
    sessions as sessions_db,
)
from bearings.db import (
    tags as tags_db,
)
from bearings.db.connection import load_schema
from bearings.web.app import create_app
from bearings.web.runner_factory import (
    InProcessRunnerRegistry,
    build_in_process_factory,
)

# ---------------------------------------------------------------------------
# Constants — every literal lives here per project rule.
# ---------------------------------------------------------------------------

E2E_DEFAULT_PORT: Final[int] = 8789  # 8788 = production-v1; +1 = test slot.
E2E_HOST: Final[str] = "127.0.0.1"
E2E_DB_FILENAME: Final[str] = "e2e.sqlite"
E2E_VAULT_DIRNAME: Final[str] = "vault"
E2E_VAULT_PLAN_FILENAME: Final[str] = "bearings-rebuild-plan.md"
E2E_VAULT_PLAN_TITLE: Final[str] = "# Bearings v1 Rebuild Plan\n"
E2E_VAULT_PLAN_BODY: Final[str] = (
    "Plan for the v1 rebuild — see `~/.claude/plans/bearings-v1-rebuild.md`."
)
E2E_VAULT_TODO_FILENAME: Final[str] = "TODO.md"
E2E_VAULT_TODO_TITLE: Final[str] = "# Sample project TODO\n"
E2E_VAULT_TODO_BODY: Final[str] = "## Open\n\n- [ ] Wire up something\n- [ ] Document the wiring\n"

# Seed sessions/tags/etc — names referenced by the spec files.
E2E_TAG_BEARINGS: Final[str] = "Bearings"
E2E_TAG_ROUTING: Final[str] = "Routing"
E2E_TAG_REBUILD: Final[str] = "v1-rebuild"

E2E_TAG_DEFAULT_MODEL: Final[str] = "sonnet"
E2E_TAG_DEFAULT_WORKING_DIR: Final[str] = "/home/test/Projects/Bearings"
E2E_TAG_COLOR_PRIMARY: Final[str] = "#3b82f6"

E2E_CHAT_TITLE_OPEN_BEARINGS: Final[str] = "Bearings v1 — wiring CI"
E2E_CHAT_TITLE_OPEN_ROUTING: Final[str] = "Routing rule editor smoke"
E2E_CHAT_TITLE_CLOSED: Final[str] = "Old planning thread"

E2E_CHECKLIST_TITLE: Final[str] = "Bearings v1 master checklist"
E2E_CHECKLIST_ITEM_LABELS: Final[tuple[str, ...]] = (
    "Item one — done",
    "Item two — paired",
    "Item three — pending",
)

E2E_MEMORY_TITLE: Final[str] = "Architect prompt fragment"
E2E_MEMORY_BODY: Final[str] = "Strict typing, no `Any`. Decide-and-move-on per decision-discipline."

E2E_QUOTA_OVERALL_PCT: Final[float] = 0.42
E2E_QUOTA_SONNET_PCT: Final[float] = 0.31

E2E_DEBUG_ROUTER_PREFIX: Final[str] = "/_e2e"

E2E_INITIAL_USER_MESSAGE: Final[str] = "Walk me through the routing eval chain for this turn."
E2E_INITIAL_ASSISTANT_MESSAGE: Final[str] = (
    "On a chat tagged `Bearings`, the system rule "
    "`always → sonnet (Workhorse default)` matched first."
)


# ---------------------------------------------------------------------------
# Debug router — Playwright drives this to inject streaming events.
# ---------------------------------------------------------------------------


class _DebugEventEnvelope(BaseModel):  # type: ignore[explicit-any]
    """Wire shape for ``POST /_e2e/sessions/{id}/emit``.

    The payload is one of the :class:`bearings.agent.events.AgentEvent`
    union members serialised as JSON. The route inflates it back into
    a dataclass via the discriminator and calls ``runner.emit(event)``
    to broadcast it to every subscribed WebSocket. Tests construct
    these payloads directly so a Playwright page can produce
    deterministic ``MessageStart`` -> ``Token`` x N -> ``MessageComplete``
    sequences without needing a real Claude SDK subprocess.

    The ``type: ignore[explicit-any]`` is the same narrow carve-out
    :mod:`bearings.config.settings` makes for ``BaseModel`` subclasses
    — Pydantic's metaclass surface includes ``Any`` regardless of how
    fully the user types the fields.
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    payload: dict[str, str | int | float | bool | None]


_EVENT_TYPES: Final[dict[str, type[AgentEvent]]] = {
    "message_start": MessageStart,
    "token": Token,
    "tool_call_start": ToolCallStart,
    "tool_output_delta": ToolOutputDelta,
    "tool_call_end": ToolCallEnd,
    "message_complete": MessageComplete,
}


def _build_debug_router() -> APIRouter:
    """Construct the ``/_e2e/*`` debug router.

    The router exposes:

    * ``GET  /_e2e/health`` — readiness probe Playwright's ``webServer``
      polls before launching tests.
    * ``POST /_e2e/sessions/{session_id}/emit`` — push an
      :class:`AgentEvent`-shaped payload into the runner's ring buffer
      and broadcast it to every subscribed WebSocket.
    * ``POST /_e2e/sessions/{session_id}/reset`` — clear the runner's
      ring buffer between specs (cheap-and-cheerful test isolation).
    """
    router = APIRouter(prefix=E2E_DEBUG_ROUTER_PREFIX)

    @router.get("/health")
    async def get_health() -> dict[str, bool]:
        return {"ok": True}

    @router.post("/sessions/{session_id}/emit")
    async def post_emit(
        session_id: str,
        envelope: _DebugEventEnvelope,
        request: Request,
    ) -> dict[str, int]:
        event_cls = _EVENT_TYPES.get(envelope.type)
        if event_cls is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown event type {envelope.type!r}; "
                f"expected one of {sorted(_EVENT_TYPES)}",
            )
        # Inflate the payload into the typed dataclass; pydantic catches
        # missing/extra fields at the boundary so a bad event surfaces
        # as a 422 the spec author can read.
        try:
            event = event_cls.model_validate({**envelope.payload, "session_id": session_id})
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        factory: RunnerFactory = request.app.state.runner_factory
        runner = await factory(session_id)
        seq = await runner.emit(event)
        return {"seq": seq}

    @router.post("/runners/reset")
    async def post_runners_reset(request: Request) -> dict[str, bool]:
        """Drop every registered runner so the next WS subscribe gets a
        fresh ring buffer. Used between Playwright specs for isolation
        — the seeded DB persists; only ephemeral runner state resets."""
        factory: RunnerFactory = request.app.state.runner_factory
        if isinstance(factory, InProcessRunnerRegistry):
            factory.close_all()
        return {"ok": True}

    return router


def _build_seed_router(seed_summary: _SeedSummary) -> APIRouter:
    """Construct the ``/_e2e/seed`` GET router that exposes seeded ids.

    Returns a JSON body so a Playwright spec can resolve session /
    tag / item ids without parsing the URL or hitting the production
    list endpoints (which would require knowing the row order).
    """
    router = APIRouter(prefix=E2E_DEBUG_ROUTER_PREFIX)

    @router.get("/seed")
    async def get_seed() -> JSONResponse:
        return JSONResponse(content=asdict(seed_summary))

    return router


# ---------------------------------------------------------------------------
# Vault fixture
# ---------------------------------------------------------------------------


def _materialise_vault(root: Path) -> VaultCfg:
    """Write deterministic plan + TODO files under ``root``."""
    plan_root = root / "plans"
    plan_root.mkdir(parents=True, exist_ok=True)
    plan_path = plan_root / E2E_VAULT_PLAN_FILENAME
    plan_path.write_text(
        E2E_VAULT_PLAN_TITLE + E2E_VAULT_PLAN_BODY + "\n",
        encoding="utf-8",
    )
    todo_root = root / "projects" / "sample"
    todo_root.mkdir(parents=True, exist_ok=True)
    todo_path = todo_root / E2E_VAULT_TODO_FILENAME
    todo_path.write_text(
        E2E_VAULT_TODO_TITLE + E2E_VAULT_TODO_BODY,
        encoding="utf-8",
    )
    return VaultCfg(
        plan_roots=(plan_root,),
        todo_globs=(str(root / "projects" / "**" / "TODO.md"),),
    )


# ---------------------------------------------------------------------------
# DB seed — every spec walks against this exact shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SeededTags:
    """Tag-id triple every spec resolves the sidebar filter against."""

    bearings: int
    routing: int
    rebuild: int


@dataclass(frozen=True)
class _SeededSessions:
    """Session-id quintuplet exposed via ``GET /_e2e/seed``."""

    chat_open_bearings: str
    chat_open_routing: str
    chat_closed: str
    checklist: str
    paired_chat: str


@dataclass(frozen=True)
class _SeededMessages:
    """Persisted user / assistant ids on the open-Bearings chat."""

    user: str
    assistant: str


@dataclass(frozen=True)
class _SeedSummary:
    """Full ids the seeder produced; serialised as JSON for tests."""

    tags: _SeededTags
    sessions: _SeededSessions
    checklist_items: tuple[int, ...]
    messages: _SeededMessages
    memory: int


async def _seed_db(connection: aiosqlite.Connection) -> _SeedSummary:
    """Apply schema + seed deterministic fixture rows.

    Returns a :class:`_SeedSummary` of seeded row ids the debug router
    exposes via ``GET /_e2e/seed`` so a spec can resolve the rows it
    cares about without hard-coding generated ids.
    """
    await load_schema(connection)
    bearings_tag = await tags_db.create(
        connection,
        name=E2E_TAG_BEARINGS,
        color=E2E_TAG_COLOR_PRIMARY,
        default_model=E2E_TAG_DEFAULT_MODEL,
        working_dir=E2E_TAG_DEFAULT_WORKING_DIR,
    )
    routing_tag = await tags_db.create(
        connection,
        name=E2E_TAG_ROUTING,
        color=E2E_TAG_COLOR_PRIMARY,
        default_model=E2E_TAG_DEFAULT_MODEL,
        working_dir=E2E_TAG_DEFAULT_WORKING_DIR,
    )
    rebuild_tag = await tags_db.create(
        connection,
        name=E2E_TAG_REBUILD,
        color=None,
        default_model=E2E_TAG_DEFAULT_MODEL,
        working_dir=E2E_TAG_DEFAULT_WORKING_DIR,
    )

    chat_open_bearings = await sessions_db.create(
        connection,
        kind=SESSION_KIND_CHAT,
        title=E2E_CHAT_TITLE_OPEN_BEARINGS,
        working_dir=E2E_TAG_DEFAULT_WORKING_DIR,
        model=E2E_TAG_DEFAULT_MODEL,
    )
    await tags_db.attach(connection, session_id=chat_open_bearings.id, tag_id=bearings_tag.id)
    await tags_db.attach(connection, session_id=chat_open_bearings.id, tag_id=rebuild_tag.id)

    chat_open_routing = await sessions_db.create(
        connection,
        kind=SESSION_KIND_CHAT,
        title=E2E_CHAT_TITLE_OPEN_ROUTING,
        working_dir=E2E_TAG_DEFAULT_WORKING_DIR,
        model=E2E_TAG_DEFAULT_MODEL,
    )
    await tags_db.attach(connection, session_id=chat_open_routing.id, tag_id=routing_tag.id)

    chat_closed = await sessions_db.create(
        connection,
        kind=SESSION_KIND_CHAT,
        title=E2E_CHAT_TITLE_CLOSED,
        working_dir=E2E_TAG_DEFAULT_WORKING_DIR,
        model=E2E_TAG_DEFAULT_MODEL,
    )
    await tags_db.attach(connection, session_id=chat_closed.id, tag_id=bearings_tag.id)
    await sessions_db.close(connection, session_id=chat_closed.id)

    # Two messages on the open chat so the conversation pane has
    # something to render even before any debug-router event fires.
    user_msg = await messages_db.insert_user(
        connection,
        session_id=chat_open_bearings.id,
        content=E2E_INITIAL_USER_MESSAGE,
    )
    assistant_msg = await messages_db.insert_user(
        connection,
        session_id=chat_open_bearings.id,
        content=E2E_INITIAL_ASSISTANT_MESSAGE,
    )

    # Tag memory under Bearings.
    memory = await memories_db.create(
        connection,
        tag_id=bearings_tag.id,
        title=E2E_MEMORY_TITLE,
        body=E2E_MEMORY_BODY,
        enabled=True,
    )

    # Checklist + items + paired-chat link on the middle item.
    checklist = await sessions_db.create(
        connection,
        kind=SESSION_KIND_CHECKLIST,
        title=E2E_CHECKLIST_TITLE,
        working_dir=E2E_TAG_DEFAULT_WORKING_DIR,
        model=E2E_TAG_DEFAULT_MODEL,
    )
    await tags_db.attach(connection, session_id=checklist.id, tag_id=bearings_tag.id)
    item_ids: list[int] = []
    for index, label in enumerate(E2E_CHECKLIST_ITEM_LABELS):
        item = await checklists_db.create(
            connection,
            checklist_id=checklist.id,
            parent_item_id=None,
            label=label,
            sort_order=index,
        )
        item_ids.append(item.id)
    # Mark first item checked.
    await checklists_db.mark_checked(connection, item_id=item_ids[0])
    # Pair the second item to a fresh chat session.
    paired_chat = await sessions_db.create(
        connection,
        kind=SESSION_KIND_CHAT,
        title=E2E_CHECKLIST_ITEM_LABELS[1],
        working_dir=E2E_TAG_DEFAULT_WORKING_DIR,
        model=E2E_TAG_DEFAULT_MODEL,
        checklist_item_id=item_ids[1],
    )
    await tags_db.attach(connection, session_id=paired_chat.id, tag_id=bearings_tag.id)
    await checklists_db.set_paired_chat(
        connection,
        item_id=item_ids[1],
        chat_session_id=paired_chat.id,
    )

    await connection.commit()

    return _SeedSummary(
        tags=_SeededTags(
            bearings=bearings_tag.id,
            routing=routing_tag.id,
            rebuild=rebuild_tag.id,
        ),
        sessions=_SeededSessions(
            chat_open_bearings=chat_open_bearings.id,
            chat_open_routing=chat_open_routing.id,
            chat_closed=chat_closed.id,
            checklist=checklist.id,
            paired_chat=paired_chat.id,
        ),
        checklist_items=tuple(item_ids),
        messages=_SeededMessages(
            user=user_msg.id,
            assistant=assistant_msg.id,
        ),
        memory=memory.id,
    )


# ---------------------------------------------------------------------------
# Quota snapshot — deterministic seed row so GET /api/quota/current returns
# 200 without needing a live ``QuotaPoller`` (production wires one via the
# CLI; the e2e harness skips it because every value is static and the
# DB-fallback path of the route already returns the latest persisted row).
# ---------------------------------------------------------------------------


async def _seed_initial_quota_snapshot(connection: aiosqlite.Connection) -> None:
    """Write one quota snapshot row so the GET /api/quota/current
    endpoint returns 200 (not 404) without waiting for the poller's
    first tick."""
    snapshot = QuotaSnapshot(
        captured_at=0,
        overall_used_pct=E2E_QUOTA_OVERALL_PCT,
        sonnet_used_pct=E2E_QUOTA_SONNET_PCT,
        overall_resets_at=None,
        sonnet_resets_at=None,
        raw_payload=json.dumps({"e2e": True}),
    )
    await record_snapshot(connection, snapshot=snapshot)
    await connection.commit()


# ---------------------------------------------------------------------------
# CLI + lifespan
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="e2e_server",
        description=(
            "Boot the Bearings v1 FastAPI app with a hermetic temp DB + "
            "vault + debug router for Playwright E2E tests."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BEARINGS_E2E_PORT", str(E2E_DEFAULT_PORT))),
        help=("TCP port to bind on 127.0.0.1 (default: env BEARINGS_E2E_PORT or 8789)"),
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=None,
        help=(
            "Optional state root for the temp DB + vault dirs. "
            "Defaults to a fresh tempfile.mkdtemp()."
        ),
    )
    return parser


def _resolve_state_root(args: argparse.Namespace) -> Path:
    if args.state_root is not None:
        root: Path = args.state_root
        root.mkdir(parents=True, exist_ok=True)
        return root
    return Path(tempfile.mkdtemp(prefix="bearings-e2e-"))


def _make_lifespan(
    db_path: Path,
    vault_cfg: VaultCfg,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Build a FastAPI lifespan that opens the long-lived DB connection
    for the app's lifetime. ``vault_cfg`` is captured for symmetry with
    the production wiring even though only the connection is reopened
    here (the cfg is already attached to ``app.state`` by
    :func:`create_app`).
    """
    del vault_cfg  # captured for parity; production wiring attaches it.

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


async def _build_app_async(
    state_root: Path,
) -> tuple[FastAPI, Path]:
    """Materialise the seeded DB + vault, return the app + DB path."""
    db_path = state_root / E2E_DB_FILENAME
    vault_root = state_root / E2E_VAULT_DIRNAME
    vault_cfg = _materialise_vault(vault_root)
    seed_connection = await aiosqlite.connect(db_path)
    try:
        await seed_connection.execute("PRAGMA foreign_keys = ON")
        seed_summary = await _seed_db(seed_connection)
        await _seed_initial_quota_snapshot(seed_connection)
    finally:
        await seed_connection.close()

    debug_router = _build_debug_router()
    seed_router = _build_seed_router(seed_summary)
    app = create_app(
        runner_factory=build_in_process_factory(),
        vault_cfg=vault_cfg,
        extra_routers=[debug_router, seed_router],
    )
    # Wire lifespan that opens the long-lived DB connection.
    app.router.lifespan_context = _make_lifespan(db_path, vault_cfg)
    return app, db_path


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    state_root = _resolve_state_root(args)
    sys.stderr.write(f"[e2e_server] state_root={state_root} port={args.port}\n")
    app, _db_path = asyncio.run(_build_app_async(state_root))
    logging.basicConfig(level=logging.WARNING)
    config = uvicorn.Config(
        app,
        host=E2E_HOST,
        port=args.port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()
    return 0


if __name__ == "__main__":  # pragma: no cover — argv plumbing
    sys.exit(main())
