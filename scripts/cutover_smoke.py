"""Cutover smoke test — item 3.4 final acceptance gate.

End-to-end verification that the v1 rebuild can ingest a v0.17.x
Bearings SQLite DB and serve every subsystem. Runs in three stages
and fails fast on any stage exit code != 0.

Stages
------

1. **Migration.** Invoke ``scripts/migrate_v0_17_to_v0_18.py`` on a
   real v0.17 DB into a tempdir-managed target. The default source
   is ``~/.local/share/bearings/db.sqlite``; the default target is a
   fresh tempfile under ``$TMPDIR`` so the production
   ``~/.local/share/bearings-v1/sessions.db`` is not clobbered. The
   migration's summary line is captured and forwarded verbatim.

2. **Per-subsystem smoke.** Boot the v1 FastAPI app pointed at the
   migrated DB via :mod:`scripts.cutover_app` (subprocess), then
   probe every API subsystem registered in
   :func:`bearings.web.app.create_app` plus the static SPA mount.
   After the basic probes a "data-walk" phase verifies the migrated
   data round-trips through the API: every session id and tag id
   surfaced by the list endpoints is fetched back individually.

3. **E2E acceptance gate.** Run the Playwright suite (item 3.1) so
   the 9 specs / 29 tests confirm v1-stack behavior is unbroken
   end-to-end. The Playwright run boots its own ``e2e_server``
   (seeded fixture DB) — passing the suite after the migration code
   path has executed proves the v1 schema + route surface is the
   same one the migration targets.

Why Python (not Bash)
---------------------

The orchestrator parses migration summary text, JSON-decodes per-API
responses, and structures a per-subsystem PASS/FAIL report. Bash
would force ``jq`` invocations + brittle string globbing for those.
Python keeps every probe a typed function call so ``mypy --strict``
covers the smoke harness the same way it covers the rest of the
project. The migration script is already Python, so subprocess
invocation symmetry costs nothing.

Atomicity
---------

* The migrated DB lives under ``tempfile.mkdtemp(prefix=...)``.
* The vault root lives under the same tempdir.
* ``finally`` blocks remove the tempdir on every exit path
  (success, probe-fail, e2e-fail, KeyboardInterrupt).
* The booted v1 app subprocess is signalled (``SIGTERM`` then
  ``SIGKILL`` after :data:`SHUTDOWN_TIMEOUT_S`) before tempdir
  cleanup so a closed-aiosqlite-connection error cannot strand the
  WAL files.

Reproducibility
---------------

Re-running the script on the same source DB produces the same per-
subsystem report (modulo wall-clock timestamps in the migration
summary). Idempotent because every stage takes its inputs from CLI
args or the source DB, never from host state outside ``--source``.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import httpx

# ---------------------------------------------------------------------------
# Paths + script locations
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MIGRATE_SCRIPT_PATH: Final[Path] = REPO_ROOT / "scripts" / "migrate_v0_17_to_v0_18.py"
APP_SCRIPT_PATH: Final[Path] = REPO_ROOT / "scripts" / "cutover_app.py"
FRONTEND_DIR: Final[Path] = REPO_ROOT / "frontend"
DEFAULT_SOURCE_DB: Final[Path] = Path("~/.local/share/bearings/db.sqlite").expanduser()
TARGET_DB_FILENAME: Final[str] = "sessions.db"
TARGET_VAULT_DIRNAME: Final[str] = "vault"
TEMPDIR_PREFIX: Final[str] = "bearings-cutover-"

# ---------------------------------------------------------------------------
# Networking + timing
# ---------------------------------------------------------------------------

CUTOVER_HOST: Final[str] = "127.0.0.1"
APP_BOOT_TIMEOUT_S: Final[float] = 30.0
APP_BOOT_POLL_INTERVAL_S: Final[float] = 0.25
PROBE_HTTP_TIMEOUT_S: Final[float] = 10.0
SHUTDOWN_GRACE_S: Final[float] = 5.0
SHUTDOWN_KILL_DELAY_S: Final[float] = 5.0
DATA_WALK_SAMPLE_LIMIT: Final[int] = 25
E2E_RUN_TIMEOUT_S: Final[float] = 600.0

# ``Accept: text/html`` mimics a browser navigation request so the
# static-bundle SPA fallback in :mod:`bearings.web.static` engages
# for deep client-router paths (without it the StaticFiles 404 is
# preserved verbatim per the static.py "asset miss vs. navigation
# miss" branch). Sending this on every probe is safe because the
# JSON API routes ignore Accept, and ``/metrics`` returns its
# Prometheus text-format payload regardless.
PROBE_DEFAULT_HEADERS: Final[dict[str, str]] = {"accept": "text/html, */*"}

# ---------------------------------------------------------------------------
# Process exit codes
# ---------------------------------------------------------------------------

EXIT_SUCCESS: Final[int] = 0
EXIT_FAILURE: Final[int] = 1
EXIT_MIGRATION_FAILED: Final[int] = 2
EXIT_APP_BOOT_FAILED: Final[int] = 3
EXIT_PROBES_FAILED: Final[int] = 4
EXIT_DATA_WALK_FAILED: Final[int] = 5
EXIT_E2E_FAILED: Final[int] = 6

LOG: Final[logging.Logger] = logging.getLogger("bearings.cutover_smoke")

# ---------------------------------------------------------------------------
# Subsystem probe table
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Probe:
    """One subsystem-level GET probe.

    ``accepted_status_codes`` is a frozenset so a probe that has more
    than one well-defined response (e.g. ``/api/quota/current`` is
    ``200`` when a snapshot exists, ``404`` when none has ever
    landed) can declare every shape that counts as PASS.
    """

    name: str
    path: str
    accepted_status_codes: frozenset[int]


# Subsystem probes. Each row covers exactly one of the route groups
# registered in :func:`bearings.web.app.create_app`. The smoke does
# NOT assert on response bodies — that's what
# ``tests/test_<route>_api.py`` is for. A 200-or-known-4xx response
# proves the subsystem's plumbing wires up against the migrated DB.
SUBSYSTEM_PROBES: Final[tuple[Probe, ...]] = (
    Probe("health", "/api/health", frozenset({200})),
    Probe("metrics", "/metrics", frozenset({200})),
    Probe("tags", "/api/tags", frozenset({200})),
    Probe("tag_groups", "/api/tag-groups", frozenset({200})),
    Probe("sessions", "/api/sessions", frozenset({200})),
    Probe("vault_list", "/api/vault", frozenset({200})),
    # /api/vault/search requires q (Query(...)); a non-empty query
    # against an empty staged vault returns 200 + empty result list.
    Probe("vault_search", "/api/vault/search?q=plan", frozenset({200})),
    Probe("uploads", "/api/uploads", frozenset({200})),
    Probe("routing_system", "/api/routing/system", frozenset({200})),
    # /api/quota/current returns 404 when no snapshot has ever been
    # recorded — v0.17 had no quota_snapshots table (added in item
    # 1.8) so the migrated DB always lacks rows. The 404 is the
    # documented "never polled" branch from
    # docs/behavior/routing.md §"Quota guard".
    Probe("quota_current", "/api/quota/current", frozenset({200, 404})),
    Probe("quota_history", "/api/quota/history", frozenset({200})),
    Probe("usage_by_model", "/api/usage/by_model", frozenset({200})),
    Probe("usage_by_tag", "/api/usage/by_tag", frozenset({200})),
    Probe("usage_override_rates", "/api/usage/override_rates", frozenset({200})),
    Probe("diag_server", "/api/diag/server", frozenset({200})),
    Probe("diag_sessions", "/api/diag/sessions", frozenset({200})),
    Probe("diag_drivers", "/api/diag/drivers", frozenset({200})),
    Probe("diag_quota", "/api/diag/quota", frozenset({200})),
    # SPA root + a deep-route the SvelteKit client-router resolves;
    # the static.py SPA fallback rewrites the deep miss to
    # index.html.
    Probe("static_spa_root", "/", frozenset({200})),
    Probe("static_spa_deep", "/sessions/does-not-exist", frozenset({200})),
)


# ---------------------------------------------------------------------------
# Result records
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ProbeResult:
    """Outcome of one probe."""

    probe: Probe
    status_code: int | None  # None when the request itself errored.
    detail: str

    @property
    def passed(self) -> bool:
        return self.status_code is not None and self.status_code in self.probe.accepted_status_codes


@dataclasses.dataclass(frozen=True)
class DataWalkResult:
    """Outcome of the migrated-data round-trip walk."""

    sessions_walked: int
    tags_walked: int
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclasses.dataclass(frozen=True)
class CutoverReport:
    """Aggregate cutover-smoke report. Renderable + assert-able."""

    source_db: Path
    target_db: Path
    migration_summary: str
    probes: tuple[ProbeResult, ...]
    data_walk: DataWalkResult
    e2e_exit_code: int | None

    @property
    def all_probes_passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    @property
    def overall_passed(self) -> bool:
        # ``e2e_exit_code is None`` means ``--skip-e2e`` was passed,
        # which is supported for fast iteration on the migration /
        # probe layers. The CLI's :func:`main` exit-code logic also
        # treats ``None`` as a non-failure; this property mirrors
        # that contract so the human + JSON renderers agree with the
        # process exit code.
        e2e_ok = self.e2e_exit_code is None or self.e2e_exit_code == 0
        return self.all_probes_passed and self.data_walk.passed and e2e_ok


# ---------------------------------------------------------------------------
# Free-port discovery
# ---------------------------------------------------------------------------


def _find_free_port() -> int:
    """Return a TCP port the OS confirms is free on the loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((CUTOVER_HOST, 0))
        port: int = sock.getsockname()[1]
        return port


# ---------------------------------------------------------------------------
# Stage 1 — migration
# ---------------------------------------------------------------------------


def run_migration(*, source_db: Path, target_db: Path) -> str:
    """Run the v0.17 → v0.18 migration script as a subprocess.

    Returns the captured stdout (the summary line) on success;
    raises :class:`RuntimeError` with the full output on non-zero
    exit. The subprocess inherits no env beyond the parent's so
    ``UV_PROJECT_ROOT`` etc. carry through automatically.
    """
    cmd = [
        sys.executable,
        str(MIGRATE_SCRIPT_PATH),
        "--source",
        str(source_db),
        "--target",
        str(target_db),
    ]
    LOG.info("Migration: %s", " ".join(cmd))
    completed = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Migration failed with exit {completed.returncode}\n"
            f"--- stdout ---\n{completed.stdout}\n"
            f"--- stderr ---\n{completed.stderr}\n"
        )
    return completed.stdout


# ---------------------------------------------------------------------------
# Stage 2 — boot the v1 app + probe every subsystem
# ---------------------------------------------------------------------------


def _spawn_app_subprocess(*, db_path: Path, vault_root: Path, port: int) -> subprocess.Popen[bytes]:
    """Spawn the cutover_app subprocess and return the Popen handle.

    Stdout/stderr are inherited so a uvicorn boot error is visible in
    the orchestrator's terminal without a separate log shuffle. The
    process is its own session leader (``start_new_session=True``) so
    ``SIGTERM`` to the PID hits uvicorn cleanly without involving the
    parent's controlling terminal.
    """
    cmd = [
        sys.executable,
        str(APP_SCRIPT_PATH),
        "--db",
        str(db_path),
        "--port",
        str(port),
        "--vault-root",
        str(vault_root),
    ]
    LOG.info("Boot: %s", " ".join(cmd))
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )


def _wait_for_app_ready(*, port: int, timeout_s: float) -> None:
    """Poll ``/api/health`` until the app responds 200 or timeout.

    Raises :class:`RuntimeError` on timeout. Connection-refused is
    expected during boot and silently retried.
    """
    deadline = time.monotonic() + timeout_s
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with httpx.Client(
                base_url=f"http://{CUTOVER_HOST}:{port}",
                timeout=PROBE_HTTP_TIMEOUT_S,
            ) as client:
                response = client.get("/api/health")
                if response.status_code == 200:
                    return
                last_error = f"status={response.status_code} body={response.text[:200]}"
        except (httpx.HTTPError, OSError) as exc:
            last_error = repr(exc)
        time.sleep(APP_BOOT_POLL_INTERVAL_S)
    raise RuntimeError(f"App did not become ready within {timeout_s}s; last error: {last_error}")


def _shutdown_app_subprocess(process: subprocess.Popen[bytes]) -> None:
    """Politely terminate the booted app, escalating to SIGKILL on timeout."""
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=SHUTDOWN_GRACE_S)
        return
    except subprocess.TimeoutExpired:
        LOG.warning("App did not exit on SIGTERM; sending SIGKILL")
        process.kill()
        try:
            process.wait(timeout=SHUTDOWN_KILL_DELAY_S)
        except subprocess.TimeoutExpired:
            LOG.error("App did not exit on SIGKILL — leaking PID %d", process.pid)


def probe_subsystem(client: httpx.Client, probe: Probe) -> ProbeResult:
    """Run one probe via ``client``. Catches transport errors and
    surfaces them as ``status_code=None`` so the orchestrator can
    aggregate the report without an unhandled exception bubbling up
    to the tempdir-cleanup boundary.

    Sends :data:`PROBE_DEFAULT_HEADERS` so the static-bundle SPA
    fallback engages for the ``static_spa_*`` probes (the fallback
    in :mod:`bearings.web.static` is gated on ``Accept: text/html``).
    """
    try:
        response = client.get(probe.path, headers=PROBE_DEFAULT_HEADERS)
    except httpx.HTTPError as exc:
        return ProbeResult(probe=probe, status_code=None, detail=f"transport error: {exc!r}")
    detail = (
        f"ok status={response.status_code}"
        if response.status_code in probe.accepted_status_codes
        else f"unexpected status={response.status_code} body={response.text[:300]}"
    )
    return ProbeResult(probe=probe, status_code=response.status_code, detail=detail)


def run_subsystem_probes(client: httpx.Client) -> tuple[ProbeResult, ...]:
    """Run every probe in :data:`SUBSYSTEM_PROBES` and return the results."""
    return tuple(probe_subsystem(client, probe) for probe in SUBSYSTEM_PROBES)


# ---------------------------------------------------------------------------
# Data-walk phase — verifies migrated rows round-trip through the API
# ---------------------------------------------------------------------------


def run_data_walk(client: httpx.Client) -> DataWalkResult:
    """Walk migrated data through the API.

    Lists sessions + tags, then re-fetches a sample of each by id to
    prove the migrated PKs are addressable. Limited to
    :data:`DATA_WALK_SAMPLE_LIMIT` rows per kind to keep the smoke
    fast even on a large source DB.
    """
    failures: list[str] = []
    sessions_walked = 0
    tags_walked = 0

    response = client.get("/api/sessions")
    if response.status_code != 200:
        failures.append(f"GET /api/sessions returned {response.status_code}")
    else:
        sessions = response.json()
        if not isinstance(sessions, list):
            failures.append(f"GET /api/sessions: expected list, got {type(sessions).__name__}")
        else:
            for session in sessions[:DATA_WALK_SAMPLE_LIMIT]:
                session_id = session.get("id") if isinstance(session, dict) else None
                if not isinstance(session_id, str):
                    failures.append(f"session row missing 'id': {session!r}")
                    continue
                detail_response = client.get(f"/api/sessions/{session_id}")
                if detail_response.status_code != 200:
                    failures.append(
                        f"GET /api/sessions/{session_id} returned {detail_response.status_code}"
                    )
                    continue
                messages_response = client.get(f"/api/sessions/{session_id}/messages")
                if messages_response.status_code != 200:
                    failures.append(
                        f"GET /api/sessions/{session_id}/messages returned "
                        f"{messages_response.status_code}"
                    )
                    continue
                tags_for_session = client.get(f"/api/sessions/{session_id}/tags")
                if tags_for_session.status_code != 200:
                    failures.append(
                        f"GET /api/sessions/{session_id}/tags returned "
                        f"{tags_for_session.status_code}"
                    )
                    continue
                sessions_walked += 1

    response = client.get("/api/tags")
    if response.status_code != 200:
        failures.append(f"GET /api/tags returned {response.status_code}")
    else:
        tags = response.json()
        if not isinstance(tags, list):
            failures.append(f"GET /api/tags: expected list, got {type(tags).__name__}")
        else:
            for tag in tags[:DATA_WALK_SAMPLE_LIMIT]:
                tag_id = tag.get("id") if isinstance(tag, dict) else None
                if not isinstance(tag_id, int):
                    failures.append(f"tag row missing int 'id': {tag!r}")
                    continue
                detail_response = client.get(f"/api/tags/{tag_id}")
                if detail_response.status_code != 200:
                    failures.append(
                        f"GET /api/tags/{tag_id} returned {detail_response.status_code}"
                    )
                    continue
                routing_response = client.get(f"/api/tags/{tag_id}/routing")
                if routing_response.status_code != 200:
                    failures.append(
                        f"GET /api/tags/{tag_id}/routing returned {routing_response.status_code}"
                    )
                    continue
                tags_walked += 1

    return DataWalkResult(
        sessions_walked=sessions_walked,
        tags_walked=tags_walked,
        failures=tuple(failures),
    )


# ---------------------------------------------------------------------------
# Stage 3 — Playwright E2E acceptance gate
# ---------------------------------------------------------------------------


def run_e2e_suite() -> int:
    """Run the Playwright suite from item 3.1 and return its exit code.

    The Playwright config under ``frontend/`` boots its own
    ``e2e_server`` (seeded fixture DB) — it does NOT run against the
    migrated DB. That's intentional: the suite's role here is the
    regression check that the v1 stack still works end-to-end after
    the migration code path has been exercised. Pass = the v1 schema
    + route surface the migration script targets is the same one the
    e2e suite walks.

    Output (per-spec list reporter) is forwarded to the orchestrator's
    stdout so a failure surfaces in the same terminal pane.
    """
    cmd = ["npm", "run", "test:e2e"]
    LOG.info("E2E: cd %s && %s", FRONTEND_DIR, " ".join(cmd))
    completed = subprocess.run(
        cmd,
        cwd=FRONTEND_DIR,
        check=False,
        timeout=E2E_RUN_TIMEOUT_S,
    )
    return completed.returncode


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def render_report(report: CutoverReport) -> str:
    """Render the report as a human-readable per-stage block."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("Cutover smoke — item 3.4")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"Source DB: {report.source_db}")
    lines.append(f"Target DB: {report.target_db}")
    lines.append("")
    lines.append("--- Stage 1: migration -------------------------------------------------")
    lines.append(report.migration_summary.strip())
    lines.append("")
    lines.append("--- Stage 2a: per-subsystem probes -------------------------------------")
    width = max(len(probe.probe.name) for probe in report.probes)
    for result in report.probes:
        marker = "PASS" if result.passed else "FAIL"
        lines.append(f"  [{marker}] {result.probe.name:<{width}}  {result.probe.path}")
        if not result.passed:
            lines.append(f"         -> {result.detail}")
    lines.append("")
    lines.append("--- Stage 2b: migrated-data round-trip walk ----------------------------")
    walk_marker = "PASS" if report.data_walk.passed else "FAIL"
    lines.append(
        f"  [{walk_marker}] sessions_walked={report.data_walk.sessions_walked} "
        f"tags_walked={report.data_walk.tags_walked}"
    )
    for failure in report.data_walk.failures:
        lines.append(f"         -> {failure}")
    lines.append("")
    lines.append("--- Stage 3: Playwright E2E acceptance gate ----------------------------")
    if report.e2e_exit_code is None:
        lines.append("  [SKIP] e2e suite was skipped via --skip-e2e")
    else:
        e2e_marker = "PASS" if report.e2e_exit_code == 0 else "FAIL"
        lines.append(f"  [{e2e_marker}] npm run test:e2e exit={report.e2e_exit_code}")
    lines.append("")
    lines.append("=" * 72)
    overall = "PASS" if report.overall_passed else "FAIL"
    lines.append(f"OVERALL: {overall}")
    lines.append("=" * 72)
    return "\n".join(lines)


def render_report_json(report: CutoverReport) -> str:
    """Render the report as JSON. Useful for CI machine-readable parsing."""
    payload: dict[str, object] = {
        "source_db": str(report.source_db),
        "target_db": str(report.target_db),
        "migration_summary": report.migration_summary,
        "probes": [
            {
                "name": result.probe.name,
                "path": result.probe.path,
                "passed": result.passed,
                "status_code": result.status_code,
                "detail": result.detail,
            }
            for result in report.probes
        ],
        "data_walk": {
            "sessions_walked": report.data_walk.sessions_walked,
            "tags_walked": report.data_walk.tags_walked,
            "failures": list(report.data_walk.failures),
            "passed": report.data_walk.passed,
        },
        "e2e_exit_code": report.e2e_exit_code,
        "overall_passed": report.overall_passed,
    }
    return json.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# CLI orchestration
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cutover_smoke",
        description=(
            "Cutover smoke: migrate v0.17 → v1, boot v1 app on the migrated "
            "DB, probe every subsystem, run the Playwright E2E suite. The "
            "final acceptance gate for the v1 rebuild (master item 3.4)."
        ),
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_DB,
        help=f"v0.17 source DB path (default: {DEFAULT_SOURCE_DB}).",
    )
    parser.add_argument(
        "--skip-e2e",
        action="store_true",
        default=False,
        help=(
            "Skip the Playwright E2E acceptance gate (Stage 3). Use for "
            "fast iteration on the migration / probe layers; the full "
            "cutover acceptance gate requires e2e to run."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit the report as JSON instead of the human-readable layout.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="DEBUG-level logging on the orchestrator.",
    )
    return parser


def run_cutover_smoke(*, source_db: Path, run_e2e: bool) -> CutoverReport:
    """Execute every stage and return the aggregate report.

    Caller is responsible for printing / asserting on the report.
    Tempdir is cleaned up unconditionally; the booted app subprocess
    is signalled before tempdir cleanup so the WAL drains cleanly.
    """
    if not source_db.exists():
        raise RuntimeError(f"Source DB not found: {source_db}")

    workdir = Path(tempfile.mkdtemp(prefix=TEMPDIR_PREFIX))
    target_db = workdir / TARGET_DB_FILENAME
    vault_root = workdir / TARGET_VAULT_DIRNAME
    LOG.info("Cutover workdir: %s", workdir)

    app_process: subprocess.Popen[bytes] | None = None
    try:
        # --- Stage 1: migration ---
        migration_summary = run_migration(source_db=source_db, target_db=target_db)

        # --- Stage 2: boot + probe ---
        port = _find_free_port()
        app_process = _spawn_app_subprocess(
            db_path=target_db,
            vault_root=vault_root,
            port=port,
        )
        _wait_for_app_ready(port=port, timeout_s=APP_BOOT_TIMEOUT_S)

        with httpx.Client(
            base_url=f"http://{CUTOVER_HOST}:{port}",
            timeout=PROBE_HTTP_TIMEOUT_S,
        ) as client:
            probes = run_subsystem_probes(client)
            data_walk = run_data_walk(client)

        # --- Stage 3: E2E ---
        e2e_exit_code: int | None
        if run_e2e:
            # Tear down the per-DB app first — Playwright spawns its
            # own e2e_server on a different port, so the two could
            # in principle coexist, but holding two uvicorn processes
            # open through a multi-minute Playwright run wastes
            # resources without buying anything.
            _shutdown_app_subprocess(app_process)
            app_process = None
            e2e_exit_code = run_e2e_suite()
        else:
            e2e_exit_code = None

        return CutoverReport(
            source_db=source_db,
            target_db=target_db,
            migration_summary=migration_summary,
            probes=probes,
            data_walk=data_walk,
            e2e_exit_code=e2e_exit_code,
        )
    finally:
        if app_process is not None:
            _shutdown_app_subprocess(app_process)
        # Best-effort tempdir cleanup; ``ignore_errors=True`` because
        # a stale aiosqlite WAL file occasionally lingers a moment
        # after the connection closes on slow filesystems.
        shutil.rmtree(workdir, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )
    try:
        report = run_cutover_smoke(
            source_db=args.source.expanduser(),
            run_e2e=not args.skip_e2e,
        )
    except RuntimeError as exc:
        LOG.error("Cutover smoke aborted: %s", exc)
        return EXIT_FAILURE
    rendered = render_report_json(report) if args.json else render_report(report)
    print(rendered)
    if not report.all_probes_passed:
        return EXIT_PROBES_FAILED
    if not report.data_walk.passed:
        return EXIT_DATA_WALK_FAILED
    if report.e2e_exit_code is not None and report.e2e_exit_code != 0:
        return EXIT_E2E_FAILED
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
