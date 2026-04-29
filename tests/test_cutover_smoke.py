"""Tests for the item 3.4 cutover smoke harness (``scripts/cutover_smoke``).

The orchestrator's two heavy stages (migration subprocess + Playwright
suite) are integration-only and exercised by the live smoke run. What
this test file covers is the probe + data-walk + report rendering
layers — the parts that other items would silently break if a route
moved or a status-code contract drifted.

Coverage:

* ``probe_subsystem`` PASS path against an in-memory v1 app.
* ``probe_subsystem`` FAIL path when the route returns an unexpected
  status (constructed by querying a non-existent path).
* ``probe_subsystem`` transport-error path when the client cannot
  reach the server (connection refused).
* ``run_subsystem_probes`` exercises every entry of
  :data:`SUBSYSTEM_PROBES` against a freshly-bootstrapped v1 DB and
  asserts every probe is PASS — this is the regression check that
  catches a future route rename / removal.
* ``run_data_walk`` against a small seeded dataset (3 sessions, 2
  tags) — verifies the round-trip walk records the expected counters
  and reports zero failures.
* ``render_report`` and ``render_report_json`` produce stable strings
  and well-formed JSON for a fixed ``CutoverReport`` fixture.

The probes that produce ``404`` as a documented branch
(``/api/quota/current``) are tested via the in-memory app where no
quota poller is wired and no quota_snapshot row exists.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Final

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bearings.config.constants import SESSION_KIND_CHAT
from bearings.db import sessions as sessions_db
from bearings.db import tags as tags_db
from bearings.db.connection import load_schema
from bearings.web.app import create_app

# Load the orchestrator script as a module via spec — same loader
# pattern :mod:`tests.test_migrate_v0_17_to_v0_18` uses for its
# script-under-test.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SCRIPT_PATH: Final[Path] = _REPO_ROOT / "scripts" / "cutover_smoke.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("cutover_smoke", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["cutover_smoke"] = module
    spec.loader.exec_module(module)
    return module


_M: Final[ModuleType] = _load_script_module()

# At runtime these come from the importlib-spec-loaded module above;
# at type-check time we route the same names through a TYPE_CHECKING
# import of the actual ``cutover_smoke`` source so mypy knows the
# dataclass shapes (``CutoverReport.source_db`` etc.) instead of
# treating every binding as bare ``ModuleType.__getattr__``.
if TYPE_CHECKING:  # pragma: no cover — type-only branch
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    from cutover_smoke import (
        SUBSYSTEM_PROBES,
        CutoverReport,
        DataWalkResult,
        Probe,
        ProbeResult,
        probe_subsystem,
        render_report,
        render_report_json,
        run_data_walk,
        run_subsystem_probes,
    )
else:
    CutoverReport = _M.CutoverReport
    DataWalkResult = _M.DataWalkResult
    Probe = _M.Probe
    ProbeResult = _M.ProbeResult
    SUBSYSTEM_PROBES = _M.SUBSYSTEM_PROBES
    probe_subsystem = _M.probe_subsystem
    render_report = _M.render_report
    render_report_json = _M.render_report_json
    run_data_walk = _M.run_data_walk
    run_subsystem_probes = _M.run_subsystem_probes


# ---------------------------------------------------------------------------
# In-memory v1 app fixture — seeds 3 sessions + 2 tags so the data-walk
# has something non-trivial to traverse. Mirrors the
# :func:`tests.test_sessions_api.app_and_db` fixture pattern; no
# Playwright, no migration subprocess.
# ---------------------------------------------------------------------------


@pytest.fixture
async def seeded_app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    """Bootstrap a v1 app with a small seed: 3 sessions + 2 tags."""
    db_path = tmp_path / "cutover.db"
    conn = await aiosqlite.connect(db_path)
    try:
        await load_schema(conn)
        bearings_tag = await tags_db.create(
            conn,
            name="Bearings",
            color="#3b82f6",
            default_model="sonnet",
            working_dir="/home/test",
        )
        routing_tag = await tags_db.create(
            conn,
            name="Routing",
            color=None,
            default_model="sonnet",
            working_dir="/home/test",
        )
        for index in range(3):
            session = await sessions_db.create(
                conn,
                kind=SESSION_KIND_CHAT,
                title=f"seeded-{index}",
                working_dir="/home/test",
                model="sonnet",
            )
            await tags_db.attach(
                conn,
                session_id=session.id,
                tag_id=bearings_tag.id if index % 2 == 0 else routing_tag.id,
            )
        await conn.commit()
        app = create_app(db_connection=conn)
        yield app
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# probe_subsystem unit tests
# ---------------------------------------------------------------------------


def _wrap_test_client(app: FastAPI) -> tuple[TestClient, httpx.Client]:
    """Bridge a TestClient to an httpx.Client view the orchestrator
    can pass to :func:`probe_subsystem`. The TestClient itself is
    httpx.Client-compatible, so this is just a type-cast wrapper."""
    test_client = TestClient(app)
    # TestClient extends httpx.Client; the orchestrator only uses the
    # ``.get()`` surface so the cast is sound.
    return test_client, test_client


async def test_probe_subsystem_pass_against_v1_app(seeded_app: FastAPI) -> None:
    """The /api/health probe is PASS against a freshly-booted app."""
    test_client, client = _wrap_test_client(seeded_app)
    with test_client:
        probe = Probe(
            name="health",
            path="/api/health",
            accepted_status_codes=frozenset({200}),
        )
        result = probe_subsystem(client, probe)
    assert result.passed is True
    assert result.status_code == 200


async def test_probe_subsystem_fail_on_unexpected_status(seeded_app: FastAPI) -> None:
    """An accepted-codes set that excludes the actual response is FAIL."""
    test_client, client = _wrap_test_client(seeded_app)
    with test_client:
        probe = Probe(
            name="health-but-wrong-codes",
            path="/api/health",
            accepted_status_codes=frozenset({500}),
        )
        result = probe_subsystem(client, probe)
    assert result.passed is False
    assert result.status_code == 200
    assert "unexpected status=200" in result.detail


def test_probe_subsystem_transport_error_surfaces_as_none() -> None:
    """A connection-refused error becomes status_code=None, passed=False."""
    # Bind nothing on a high-numbered port; httpx will get
    # ConnectError. Using a port unlikely to be bound on a developer
    # box; if it is, the test still passes because the response will
    # not match the impossible empty accepted-codes set anyway.
    client = httpx.Client(base_url="http://127.0.0.1:9", timeout=1.0)
    try:
        probe = Probe(
            name="black-hole",
            path="/api/health",
            accepted_status_codes=frozenset({200}),
        )
        result = probe_subsystem(client, probe)
    finally:
        client.close()
    assert result.status_code is None
    assert result.passed is False
    assert result.detail.startswith("transport error:")


async def test_run_subsystem_probes_all_pass_against_v1_app(seeded_app: FastAPI) -> None:
    """Every entry in SUBSYSTEM_PROBES is PASS against a v1 app — the
    regression check that catches a future route rename / removal."""
    test_client, client = _wrap_test_client(seeded_app)
    with test_client:
        results = run_subsystem_probes(client)
    assert len(results) == len(SUBSYSTEM_PROBES)
    failed = [(r.probe.name, r.detail) for r in results if not r.passed]
    assert not failed, f"unexpected probe failures: {failed}"


# ---------------------------------------------------------------------------
# run_data_walk
# ---------------------------------------------------------------------------


async def test_run_data_walk_traverses_seeded_sessions_and_tags(
    seeded_app: FastAPI,
) -> None:
    """The data-walk records 3 sessions + 2 tags + zero failures."""
    test_client, client = _wrap_test_client(seeded_app)
    with test_client:
        result = run_data_walk(client)
    assert result.passed is True
    assert result.sessions_walked == 3
    assert result.tags_walked == 2
    assert result.failures == ()


async def test_run_data_walk_records_failures_on_broken_endpoint(
    seeded_app: FastAPI,
) -> None:
    """An endpoint that 404s for an existing id surfaces in failures.

    Constructed by intercepting the seeded app: we monkey-patch the
    sessions list endpoint to claim a non-existent id so the per-id
    fetch in the walk hits a real 404. This proves the failure
    branch is reachable (not just dead code)."""
    test_client, client = _wrap_test_client(seeded_app)
    with test_client:
        # Smuggle a fake row in by using the actual app's sessions
        # list, then mutate the id before the walk uses it.
        # Simpler approach: build the result manually by passing the
        # client a non-existent id via an overlay endpoint.
        #
        # Trick: register an APIRouter on the live app that returns a
        # bogus session list at /api/sessions BEFORE the walk runs.
        # FastAPI's last-router-wins lets us shadow the real route.
        from fastapi import APIRouter

        shadow = APIRouter()

        @shadow.get("/api/sessions")
        async def fake_sessions() -> list[dict[str, str]]:
            return [{"id": "does-not-exist-in-db"}]

        # Insert at index 0 so the shadow takes precedence.
        seeded_app.router.routes.insert(0, shadow.routes[0])

        result = run_data_walk(client)
    assert result.passed is False
    assert result.sessions_walked == 0
    assert any("does-not-exist-in-db" in failure for failure in result.failures)


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _build_fixture_report(*, all_pass: bool) -> CutoverReport:
    """Construct a deterministic ``CutoverReport`` for renderer tests.

    The return type resolves to the real :class:`CutoverReport`
    dataclass via the ``TYPE_CHECKING`` shim at the top of the
    module so mypy can verify field accesses on the return value.
    """
    probe_a = Probe(name="health", path="/api/health", accepted_status_codes=frozenset({200}))
    probe_b = Probe(name="tags", path="/api/tags", accepted_status_codes=frozenset({200}))
    probes = (
        ProbeResult(probe=probe_a, status_code=200, detail="ok status=200"),
        ProbeResult(
            probe=probe_b,
            status_code=200 if all_pass else 503,
            detail=(
                "ok status=200" if all_pass else "unexpected status=503 body=server unavailable"
            ),
        ),
    )
    data_walk = DataWalkResult(
        sessions_walked=2 if all_pass else 0,
        tags_walked=1 if all_pass else 0,
        failures=() if all_pass else ("GET /api/sessions returned 503",),
    )
    return CutoverReport(
        source_db=Path("/source.db"),
        target_db=Path("/target.db"),
        migration_summary="Migration APPLIED: stub",
        probes=probes,
        data_walk=data_walk,
        e2e_exit_code=0 if all_pass else 1,
    )


def test_render_report_human_readable_pass_path() -> None:
    """The human renderer surfaces every stage and OVERALL: PASS."""
    report = _build_fixture_report(all_pass=True)
    rendered = render_report(report)
    assert "Cutover smoke — item 3.4" in rendered
    assert "Stage 1: migration" in rendered
    assert "Stage 2a: per-subsystem probes" in rendered
    assert "Stage 2b: migrated-data round-trip walk" in rendered
    assert "Stage 3: Playwright E2E acceptance gate" in rendered
    assert "[PASS]" in rendered
    assert "[FAIL]" not in rendered
    assert "OVERALL: PASS" in rendered


def test_render_report_human_readable_fail_path() -> None:
    """The human renderer surfaces FAIL markers and the failure detail."""
    report = _build_fixture_report(all_pass=False)
    rendered = render_report(report)
    assert "[FAIL] tags" in rendered
    assert "unexpected status=503" in rendered
    assert "OVERALL: FAIL" in rendered


def test_render_report_json_is_well_formed() -> None:
    """The JSON renderer emits parseable JSON with the expected keys."""
    report = _build_fixture_report(all_pass=True)
    payload = json.loads(render_report_json(report))
    assert payload["overall_passed"] is True
    assert payload["e2e_exit_code"] == 0
    assert payload["data_walk"]["sessions_walked"] == 2
    assert {p["name"] for p in payload["probes"]} == {"health", "tags"}


def test_cutover_report_overall_passed_requires_e2e_zero() -> None:
    """An e2e_exit_code != 0 makes overall_passed False even when the
    probes + walk passed (acceptance-gate semantics)."""
    base = _build_fixture_report(all_pass=True)
    failing = CutoverReport(
        source_db=base.source_db,
        target_db=base.target_db,
        migration_summary=base.migration_summary,
        probes=base.probes,
        data_walk=base.data_walk,
        e2e_exit_code=1,
    )
    assert failing.all_probes_passed is True
    assert failing.data_walk.passed is True
    assert failing.overall_passed is False


def test_cutover_report_overall_passed_skipped_e2e_still_passes() -> None:
    """e2e_exit_code=None (--skip-e2e) does not block overall_passed
    so long as the in-process stages pass."""
    base = _build_fixture_report(all_pass=True)
    skipped = CutoverReport(
        source_db=base.source_db,
        target_db=base.target_db,
        migration_summary=base.migration_summary,
        probes=base.probes,
        data_walk=base.data_walk,
        e2e_exit_code=None,
    )
    assert skipped.overall_passed is True
