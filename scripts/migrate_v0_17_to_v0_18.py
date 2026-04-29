"""Migrate a v0.17.x Bearings database to the v0.18 (v1 rebuild) schema.

This is the item-3.2 migration script. It reads a v0.17.x SQLite database
(default ``~/.local/share/bearings/db.sqlite`` — note the v0.17.x file is
literally ``db.sqlite``; the executor session description's
``sessions.db`` was outdated and the script introspects the on-disk
artifact directly per the reference-read protocol), applies the v1
schema to a target path (default ``~/.local/share/bearings-v1/sessions.db``),
and copies + transforms each user-data table.

CLI surface
-----------

* ``--source PATH`` — v0.17.x DB. Opened **read-only** via SQLite's URI
  mode ``file:<path>?mode=ro&immutable=1`` so the original cannot be
  damaged by a faulty migration.
* ``--target PATH`` — v1 DB. Created if missing; v1 schema is applied
  via :data:`SCHEMA_PATH` (the canonical ``src/bearings/db/schema.sql``,
  same file the runtime bootstrap uses) before any row work begins.
* ``--dry-run`` — Apply transformations inside a transaction, then
  ``ROLLBACK`` so the on-disk target is unchanged. The summary still
  reflects exactly which rows would land. Re-running on the same
  (source, target) pair is idempotent.
* ``-v`` / ``--verbose`` — DEBUG logging for per-row decisions.

Reasoning trail
---------------

**Sync ``sqlite3`` over async ``aiosqlite``.** The script is a one-shot
CLI with no event loop to share. Sync ``sqlite3`` keeps the call sites
linear (no ``async with`` plumbing in tests, no ``asyncio.run`` wrapper
around the entrypoint) and makes the transaction model explicit
(``BEGIN IMMEDIATE`` / ``COMMIT`` / ``ROLLBACK`` are stdlib calls). The
runtime path uses ``aiosqlite`` because the FastAPI request lifecycle
runs on an event loop; that constraint does not apply here.

**Atomicity.** All writes happen inside a single ``BEGIN IMMEDIATE``
transaction on the target. ``--dry-run`` issues ``ROLLBACK`` at the end;
a real run issues ``COMMIT``; any unhandled exception triggers
``ROLLBACK`` then re-raises so a partial migration cannot land. WAL
mode is unnecessary for a one-shot script and would only help if a
concurrent reader were attached, which is not a documented v0.18
operating mode.

**Idempotency.** Tables with stable primary keys (sessions, messages,
session_tags, checklist_items, checkpoints, tags) use ``INSERT OR
IGNORE`` keyed on the v0.17 PK so a re-run is a no-op. Tables whose v1
shape uses ``AUTOINCREMENT`` ids (tag_memories, templates,
auto_driver_runs) use a natural-key existence check before insert:

* ``tag_memories``: ``(tag_id, title)`` where title is the sentinel
  :data:`LEGACY_TAG_MEMORY_TITLE`.
* ``templates``: ``name`` (UNIQUE in the v1 schema).
* ``auto_driver_runs``: ``(checklist_id, started_at)``.

The ``checklists.notes`` → ``sessions.description`` merge only fires
when the v1 description is currently NULL or empty; a re-run finds the
sentinel-prefixed description already populated and skips.

**Backfill (per ``docs/model-routing-v1-spec.md`` §5).** Every assistant
message gets ``routing_source = 'unknown_legacy'`` so the override-rate
aggregator (item 1.8) filters it out of analytics. Every other
routing-decision and per-model-usage column is NULL. The legacy flat
``input_tokens`` / ``output_tokens`` / ``cache_read_tokens`` columns
carry forward verbatim (kept nullable on v1 per arch §4.7
``Optional[int]``). ``advisor_calls_count`` falls back to the schema's
``DEFAULT 0`` per spec §5 verbatim ALTER. NULL session titles backfill
to the empty string (v1 ``title TEXT NOT NULL`` admits ``''``).

**Tables intentionally dropped.** ``artifacts``, ``tool_calls``,
``preferences``, ``reorg_audits``, ``schema_migrations`` have no v1
home; their source row counts are surfaced in the summary so the user
can confirm nothing unexpected is being lost.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# v0.17.x ships its DB at ``~/.local/share/bearings/db.sqlite``. The
# executor session description carried the older ``sessions.db`` name —
# kept here as the v1 default target only, since v1 (item 0.5) renamed
# the on-disk file to ``sessions.db``.
DEFAULT_SOURCE_PATH: Final[Path] = Path("~/.local/share/bearings/db.sqlite").expanduser()
DEFAULT_TARGET_PATH: Final[Path] = Path("~/.local/share/bearings-v1/sessions.db").expanduser()

# The canonical v1 schema. Resolved at import time so a moved/renamed
# schema produces a clear error before any I/O.
SCHEMA_PATH: Final[Path] = (
    Path(__file__).resolve().parent.parent / "src" / "bearings" / "db" / "schema.sql"
)

# ---------------------------------------------------------------------------
# Backfill / placeholder values
# ---------------------------------------------------------------------------

# Spec §5 sentinel — assistant messages migrated from a pre-routing v0.17
# DB carry this in ``messages.routing_source`` so the override-rate
# aggregator filters them out of rule-rate math.
LEGACY_ROUTING_SOURCE: Final[str] = "unknown_legacy"

# v1 ``tag_memories`` requires a non-null ``title``; v0.17 only carried
# a ``content`` blob. Imported rows get this deterministic title so a
# re-run can detect existence by ``(tag_id, title)``.
LEGACY_TAG_MEMORY_TITLE: Final[str] = "Imported from v0.17"

# Prefix written into ``sessions.description`` when a v0.17
# ``checklists.notes`` value gets merged in. Re-runs detect the sentinel
# and skip; a user-typed description that doesn't carry the sentinel is
# never overwritten.
LEGACY_NOTES_DESCRIPTION_SENTINEL: Final[str] = "[Migrated v0.17 checklist notes]"

# v1 ``sessions.title TEXT NOT NULL`` — v0.17 allowed NULL. Empty string
# satisfies the constraint and renders as a blank title in the UI (the
# row isn't lost).
EMPTY_TITLE_BACKFILL: Final[str] = ""

# Default JSON-encoded tag-name array for migrated templates whose
# v0.17 ``tag_ids_json`` resolves to an empty list.
EMPTY_TAG_NAMES_JSON: Final[str] = "[]"

# Template column defaults — v0.17 ``session_templates`` carried fewer
# columns; the rest backfill to the v1 schema's documented defaults.
DEFAULT_TEMPLATE_PERMISSION_PROFILE: Final[str] = "standard"
DEFAULT_TEMPLATE_EFFORT_LEVEL: Final[str] = "auto"
DEFAULT_TEMPLATE_ADVISOR_MAX_USES: Final[int] = 5
DEFAULT_TEMPLATE_MODEL_FALLBACK: Final[str] = "sonnet"

# auto_driver_runs column defaults for fields v0.17 didn't track.
DEFAULT_AUTO_DRIVER_RUN_FAILURE_POLICY: Final[str] = "halt"
DEFAULT_AUTO_DRIVER_RUN_VISIT_EXISTING: Final[int] = 0

# When a v0.17 ``auto_run_state.state`` value isn't in the v1 alphabet,
# fall back to ``errored`` rather than silently dropping the row — the
# counters carry useful audit info even if the state name has shifted.
LEGACY_AUTO_DRIVER_RUN_STATE_FALLBACK: Final[str] = "errored"

# ---------------------------------------------------------------------------
# v1 alphabets (mirror the SQL CHECK constraints in ``schema.sql``)
# ---------------------------------------------------------------------------

VALID_V1_SESSION_KINDS: Final[frozenset[str]] = frozenset({"chat", "checklist"})
VALID_V1_MESSAGE_ROLES: Final[frozenset[str]] = frozenset({"user", "assistant", "system", "tool"})
VALID_V1_AUTO_DRIVER_RUN_STATES: Final[frozenset[str]] = frozenset(
    {"idle", "running", "paused", "finished", "errored"}
)

# Tables that exist in v0.17 but have no v1 home. Their source row
# counts are surfaced so the user knows what is being dropped.
DROPPED_V0_17_TABLES: Final[tuple[str, ...]] = (
    "artifacts",
    "tool_calls",
    "preferences",
    "reorg_audits",
    "schema_migrations",
)

# Tables that exist in v0.17 and migrate without a same-name target
# (notes are merged elsewhere; the per-table row in the summary uses
# the v1-side label).
ASSISTANT_ROLE: Final[str] = "assistant"

# ---------------------------------------------------------------------------
# Process-exit codes
# ---------------------------------------------------------------------------

EXIT_SUCCESS: Final[int] = 0
EXIT_FAILURE: Final[int] = 1

LOG: Final[logging.Logger] = logging.getLogger("bearings.migrate_v0_17_to_v0_18")


class MigrationError(RuntimeError):
    """Raised on physical / reachability problems with the source DB."""


# ---------------------------------------------------------------------------
# Summary types
# ---------------------------------------------------------------------------


@dataclass
class TableSummary:
    """Per-table migration counters surfaced in the summary line.

    ``inserted`` and ``skipped_existing`` together account for every
    valid source row; ``skipped_invalid`` covers rows whose v0.17
    payload could not be coerced into the v1 alphabet (e.g. a
    ``messages.role`` value outside the v1 CHECK).
    """

    name: str
    source_rows: int = 0
    inserted: int = 0
    skipped_existing: int = 0
    skipped_invalid: int = 0


@dataclass
class MigrationSummary:
    """Aggregate summary of one migration run."""

    source_path: Path
    target_path: Path
    dry_run: bool
    tables: list[TableSummary] = field(default_factory=list)
    dropped_tables: list[tuple[str, int]] = field(default_factory=list)

    def render(self) -> str:
        """Human-readable summary, one row per table."""
        lines: list[str] = []
        mode = "DRY-RUN" if self.dry_run else "APPLIED"
        lines.append(f"Migration {mode}: {self.source_path} -> {self.target_path}")
        for table in self.tables:
            lines.append(
                f"  {table.name:<28} "
                f"source={table.source_rows:>6}  "
                f"inserted={table.inserted:>6}  "
                f"skipped_existing={table.skipped_existing:>6}  "
                f"skipped_invalid={table.skipped_invalid:>6}"
            )
        for name, count in self.dropped_tables:
            lines.append(f"  {name:<28} source={count:>6}  (dropped — no v1 home)")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def _open_source_readonly(path: Path) -> sqlite3.Connection:
    """Open the v0.17 DB read-only via SQLite's immutable URI form."""
    if not path.exists():
        raise MigrationError(f"Source DB not found: {path}")
    uri = f"file:{path}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _open_target(path: Path) -> sqlite3.Connection:
    """Open the v1 DB read/write, creating the parent directory if needed.

    ``isolation_level=None`` puts the connection in explicit-transaction
    mode so the script controls ``BEGIN`` / ``COMMIT`` / ``ROLLBACK``
    boundaries directly rather than fighting Python's implicit DML
    transactions.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    return connection


def _apply_v1_schema(connection: sqlite3.Connection) -> None:
    """Apply ``schema.sql`` to ``connection``. Idempotent on re-init."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(schema_sql)


# ---------------------------------------------------------------------------
# Per-table migration functions
# ---------------------------------------------------------------------------


def _migrate_tags(src: sqlite3.Connection, tgt: sqlite3.Connection) -> TableSummary:
    """tags: drop pinned/sort_order/tag_group; updated_at = created_at."""
    summary = TableSummary(name="tags")
    rows = src.execute(
        "SELECT id, name, color, default_model, default_working_dir, created_at FROM tags"
    ).fetchall()
    summary.source_rows = len(rows)
    for row in rows:
        cursor = tgt.execute(
            "INSERT OR IGNORE INTO tags "
            "(id, name, color, default_model, working_dir, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                row["id"],
                row["name"],
                row["color"],
                row["default_model"],
                row["default_working_dir"],
                row["created_at"],
                row["created_at"],
            ),
        )
        if cursor.rowcount > 0:
            summary.inserted += 1
        else:
            summary.skipped_existing += 1
    return summary


def _migrate_sessions(src: sqlite3.Connection, tgt: sqlite3.Connection) -> TableSummary:
    """sessions: drop sdk_session_id; backfill NULL title to ''."""
    summary = TableSummary(name="sessions")
    rows = src.execute(
        "SELECT id, kind, title, description, session_instructions, working_dir, "
        "model, permission_mode, max_budget_usd, total_cost_usd, "
        "last_context_pct, last_context_tokens, last_context_max, "
        "pinned, error_pending, checklist_item_id, "
        "created_at, updated_at, last_viewed_at, last_completed_at, closed_at "
        "FROM sessions"
    ).fetchall()
    summary.source_rows = len(rows)
    for row in rows:
        if row["kind"] not in VALID_V1_SESSION_KINDS:
            LOG.warning("skipping session %s: kind=%r outside v1 alphabet", row["id"], row["kind"])
            summary.skipped_invalid += 1
            continue
        title = row["title"] if row["title"] is not None else EMPTY_TITLE_BACKFILL
        # ``message_count`` is left at the schema's DEFAULT 0 here and
        # backfilled by :func:`_recompute_session_message_counts` after
        # the messages migration has run, so the subquery has rows to
        # count against.
        cursor = tgt.execute(
            "INSERT OR IGNORE INTO sessions "
            "(id, kind, title, description, session_instructions, working_dir, "
            "model, permission_mode, max_budget_usd, total_cost_usd, "
            "last_context_pct, last_context_tokens, last_context_max, "
            "pinned, error_pending, checklist_item_id, "
            "created_at, updated_at, last_viewed_at, last_completed_at, closed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["id"],
                row["kind"],
                title,
                row["description"],
                row["session_instructions"],
                row["working_dir"],
                row["model"],
                row["permission_mode"],
                row["max_budget_usd"],
                row["total_cost_usd"],
                row["last_context_pct"],
                row["last_context_tokens"],
                row["last_context_max"],
                row["pinned"],
                row["error_pending"],
                row["checklist_item_id"],
                row["created_at"],
                row["updated_at"],
                row["last_viewed_at"],
                row["last_completed_at"],
                row["closed_at"],
            ),
        )
        if cursor.rowcount > 0:
            summary.inserted += 1
        else:
            summary.skipped_existing += 1
    return summary


def _migrate_session_tags(src: sqlite3.Connection, tgt: sqlite3.Connection) -> TableSummary:
    """session_tags: same shape — direct copy."""
    summary = TableSummary(name="session_tags")
    rows = src.execute("SELECT session_id, tag_id, created_at FROM session_tags").fetchall()
    summary.source_rows = len(rows)
    for row in rows:
        cursor = tgt.execute(
            "INSERT OR IGNORE INTO session_tags (session_id, tag_id, created_at) VALUES (?, ?, ?)",
            (row["session_id"], row["tag_id"], row["created_at"]),
        )
        if cursor.rowcount > 0:
            summary.inserted += 1
        else:
            summary.skipped_existing += 1
    return summary


def _migrate_tag_memories(src: sqlite3.Connection, tgt: sqlite3.Connection) -> TableSummary:
    """tag_memories: v0.17 (tag_id, content, updated_at) → v1
    (tag_id, title=sentinel, body=content, enabled=1, timestamps).

    v1 has no UNIQUE on (tag_id, title); idempotency is enforced by an
    explicit existence check.
    """
    summary = TableSummary(name="tag_memories")
    rows = src.execute("SELECT tag_id, content, updated_at FROM tag_memories").fetchall()
    summary.source_rows = len(rows)
    for row in rows:
        existing = tgt.execute(
            "SELECT 1 FROM tag_memories WHERE tag_id = ? AND title = ?",
            (row["tag_id"], LEGACY_TAG_MEMORY_TITLE),
        ).fetchone()
        if existing is not None:
            summary.skipped_existing += 1
            continue
        tgt.execute(
            "INSERT INTO tag_memories "
            "(tag_id, title, body, enabled, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, ?, ?)",
            (
                row["tag_id"],
                LEGACY_TAG_MEMORY_TITLE,
                row["content"],
                row["updated_at"],
                row["updated_at"],
            ),
        )
        summary.inserted += 1
    return summary


def _migrate_checklist_items(src: sqlite3.Connection, tgt: sqlite3.Connection) -> TableSummary:
    """checklist_items: column shape unchanged between v0.17 and v1."""
    summary = TableSummary(name="checklist_items")
    rows = src.execute(
        "SELECT id, checklist_id, parent_item_id, label, notes, sort_order, "
        "checked_at, chat_session_id, blocked_at, blocked_reason_category, "
        "blocked_reason_text, created_at, updated_at FROM checklist_items"
    ).fetchall()
    summary.source_rows = len(rows)
    for row in rows:
        cursor = tgt.execute(
            "INSERT OR IGNORE INTO checklist_items "
            "(id, checklist_id, parent_item_id, label, notes, sort_order, "
            "checked_at, chat_session_id, blocked_at, blocked_reason_category, "
            "blocked_reason_text, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["id"],
                row["checklist_id"],
                row["parent_item_id"],
                row["label"],
                row["notes"],
                row["sort_order"],
                row["checked_at"],
                row["chat_session_id"],
                row["blocked_at"],
                row["blocked_reason_category"],
                row["blocked_reason_text"],
                row["created_at"],
                row["updated_at"],
            ),
        )
        if cursor.rowcount > 0:
            summary.inserted += 1
        else:
            summary.skipped_existing += 1
    return summary


def _migrate_messages(src: sqlite3.Connection, tgt: sqlite3.Connection) -> TableSummary:
    """messages: drop thinking/cache_creation_tokens/replay_attempted_at/
    pinned/hidden_from_context/attachments. Assistant rows get
    routing_source='unknown_legacy'; per-model usage NULL; legacy flat
    input/output/cache_read carry forward verbatim per spec §5."""
    summary = TableSummary(name="messages")
    rows = src.execute(
        "SELECT id, session_id, role, content, created_at, "
        "input_tokens, output_tokens, cache_read_tokens FROM messages"
    ).fetchall()
    summary.source_rows = len(rows)
    for row in rows:
        if row["role"] not in VALID_V1_MESSAGE_ROLES:
            LOG.warning("skipping message %s: role=%r outside v1 alphabet", row["id"], row["role"])
            summary.skipped_invalid += 1
            continue
        routing_source = LEGACY_ROUTING_SOURCE if row["role"] == ASSISTANT_ROLE else None
        cursor = tgt.execute(
            "INSERT OR IGNORE INTO messages "
            "(id, session_id, role, content, created_at, "
            "executor_model, advisor_model, effort_level, routing_source, routing_reason, "
            "matched_rule_id, executor_input_tokens, executor_output_tokens, "
            "advisor_input_tokens, advisor_output_tokens, cache_read_tokens, "
            "input_tokens, output_tokens) "
            "VALUES (?, ?, ?, ?, ?, "
            "NULL, NULL, NULL, ?, NULL, "
            "NULL, NULL, NULL, NULL, NULL, ?, ?, ?)",
            (
                row["id"],
                row["session_id"],
                row["role"],
                row["content"],
                row["created_at"],
                routing_source,
                row["cache_read_tokens"],
                row["input_tokens"],
                row["output_tokens"],
            ),
        )
        if cursor.rowcount > 0:
            summary.inserted += 1
        else:
            summary.skipped_existing += 1
    return summary


def _migrate_checkpoints(src: sqlite3.Connection, tgt: sqlite3.Connection) -> TableSummary:
    """checkpoints: v1 message_id is NOT NULL; rows with NULL message_id
    are skipped (the v1 schema cannot represent them) and surfaced in
    the ``skipped_invalid`` counter."""
    summary = TableSummary(name="checkpoints")
    rows = src.execute(
        "SELECT id, session_id, message_id, label, created_at FROM checkpoints"
    ).fetchall()
    summary.source_rows = len(rows)
    for row in rows:
        if row["message_id"] is None or row["label"] is None:
            LOG.warning(
                "skipping checkpoint %s: NULL message_id or label (v1 declares both NOT NULL)",
                row["id"],
            )
            summary.skipped_invalid += 1
            continue
        cursor = tgt.execute(
            "INSERT OR IGNORE INTO checkpoints "
            "(id, session_id, message_id, label, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                row["id"],
                row["session_id"],
                row["message_id"],
                row["label"],
                row["created_at"],
            ),
        )
        if cursor.rowcount > 0:
            summary.inserted += 1
        else:
            summary.skipped_existing += 1
    return summary


def _migrate_session_templates(src: sqlite3.Connection, tgt: sqlite3.Connection) -> TableSummary:
    """session_templates → templates. v0.17 ``id`` (TEXT) is dropped;
    v1 mints an INTEGER autoincrement. v0.17 ``body`` lands in v1
    ``system_prompt_baseline``; ``session_instructions`` has no v1 home
    and is dropped (the relationship between body / session_instructions
    in v0.17 was historical noise per session-templates v0.17 design).
    Unique key in v1 is ``name``; ``INSERT OR IGNORE`` makes re-runs
    idempotent.

    ``model`` falls back to :data:`DEFAULT_TEMPLATE_MODEL_FALLBACK` when
    v0.17 left it NULL; v1 declares ``model TEXT NOT NULL``.
    ``tag_ids_json`` from v0.17 is intentionally not resolved to names —
    the spec for v1 templates (item 1.10 + behavior/chat.md) declares
    tag bindings are per-name and re-resolved on apply, so a fresh
    user-driven re-tag is the right v0.18 behavior. Migrated templates
    land with empty ``tag_names_json``.
    """
    summary = TableSummary(name="templates")
    rows = src.execute(
        "SELECT name, body, working_dir, model, created_at FROM session_templates"
    ).fetchall()
    summary.source_rows = len(rows)
    for row in rows:
        existing = tgt.execute("SELECT 1 FROM templates WHERE name = ?", (row["name"],)).fetchone()
        if existing is not None:
            summary.skipped_existing += 1
            continue
        model = row["model"] or DEFAULT_TEMPLATE_MODEL_FALLBACK
        tgt.execute(
            "INSERT INTO templates "
            "(name, description, model, advisor_model, advisor_max_uses, "
            "effort_level, permission_profile, system_prompt_baseline, "
            "working_dir_default, tag_names_json, created_at, updated_at) "
            "VALUES (?, NULL, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["name"],
                model,
                DEFAULT_TEMPLATE_ADVISOR_MAX_USES,
                DEFAULT_TEMPLATE_EFFORT_LEVEL,
                DEFAULT_TEMPLATE_PERMISSION_PROFILE,
                row["body"],
                row["working_dir"],
                EMPTY_TAG_NAMES_JSON,
                row["created_at"],
                row["created_at"],
            ),
        )
        summary.inserted += 1
    return summary


def _migrate_auto_driver_runs(src: sqlite3.Connection, tgt: sqlite3.Connection) -> TableSummary:
    """auto_run_state → auto_driver_runs.

    v0.17 keyed by ``checklist_session_id`` (one row per checklist);
    v1 uses an autoincrement ``id`` and lets multiple historical runs
    coexist (per docs/behavior/checklists.md). Idempotency: natural key
    ``(checklist_id, started_at)``. v0.17 state values outside the v1
    alphabet fall back to :data:`LEGACY_AUTO_DRIVER_RUN_STATE_FALLBACK`
    so the counters survive even if the state name shifted.

    ``items_attempted`` (new in v1) backfills as
    ``items_completed + items_failed + items_blocked + items_skipped``
    so the post-migration arithmetic on the status line is consistent.
    ``failure_policy`` and ``visit_existing`` use the v1 defaults; the
    v0.17 ``config_json`` blob is not parsed because its shape was
    informal and the safe default ``halt`` matches v0.17's documented
    behavior.
    """
    summary = TableSummary(name="auto_driver_runs")
    rows = src.execute(
        "SELECT checklist_session_id, state, items_completed, items_failed, "
        "items_skipped, items_blocked, legs_spawned, failed_item_id, "
        "failure_reason, created_at, updated_at FROM auto_run_state"
    ).fetchall()
    summary.source_rows = len(rows)
    for row in rows:
        state = row["state"]
        if state not in VALID_V1_AUTO_DRIVER_RUN_STATES:
            LOG.warning(
                "auto_run_state for checklist %s: state=%r outside v1 alphabet — "
                "falling back to %r",
                row["checklist_session_id"],
                state,
                LEGACY_AUTO_DRIVER_RUN_STATE_FALLBACK,
            )
            state = LEGACY_AUTO_DRIVER_RUN_STATE_FALLBACK
        existing = tgt.execute(
            "SELECT 1 FROM auto_driver_runs WHERE checklist_id = ? AND started_at = ?",
            (row["checklist_session_id"], row["created_at"]),
        ).fetchone()
        if existing is not None:
            summary.skipped_existing += 1
            continue
        items_attempted = (
            (row["items_completed"] or 0)
            + (row["items_failed"] or 0)
            + (row["items_blocked"] or 0)
            + (row["items_skipped"] or 0)
        )
        tgt.execute(
            "INSERT INTO auto_driver_runs "
            "(checklist_id, state, failure_policy, visit_existing, "
            "items_completed, items_failed, items_blocked, items_skipped, "
            "items_attempted, legs_spawned, current_item_id, "
            "outcome, outcome_reason, started_at, updated_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL)",
            (
                row["checklist_session_id"],
                state,
                DEFAULT_AUTO_DRIVER_RUN_FAILURE_POLICY,
                DEFAULT_AUTO_DRIVER_RUN_VISIT_EXISTING,
                row["items_completed"] or 0,
                row["items_failed"] or 0,
                row["items_blocked"] or 0,
                row["items_skipped"] or 0,
                items_attempted,
                row["legs_spawned"] or 0,
                row["failed_item_id"],
                row["failure_reason"],
                row["created_at"],
                row["updated_at"],
            ),
        )
        summary.inserted += 1
    return summary


def _apply_checklist_notes_to_descriptions(
    src: sqlite3.Connection, tgt: sqlite3.Connection
) -> TableSummary:
    """Merge v0.17 ``checklists.notes`` into v1 ``sessions.description``
    for matching checklist-kind sessions.

    v1 has no separate ``checklists`` table — checklist-kind metadata
    lives on the ``sessions`` row. The merge only fires when the v1
    description is currently NULL or empty so a user-typed description
    is never overwritten. Re-runs detect the
    :data:`LEGACY_NOTES_DESCRIPTION_SENTINEL` prefix and skip.
    """
    summary = TableSummary(name="sessions(notes_merge)")
    rows = src.execute(
        "SELECT session_id, notes FROM checklists WHERE notes IS NOT NULL AND notes != ''"
    ).fetchall()
    summary.source_rows = len(rows)
    for row in rows:
        target_session = tgt.execute(
            "SELECT description FROM sessions WHERE id = ?",
            (row["session_id"],),
        ).fetchone()
        if target_session is None:
            LOG.warning(
                "checklists.notes for %s: no matching v1 session row — skipping",
                row["session_id"],
            )
            summary.skipped_invalid += 1
            continue
        existing_description = target_session["description"]
        if existing_description not in (None, ""):
            summary.skipped_existing += 1
            continue
        merged = f"{LEGACY_NOTES_DESCRIPTION_SENTINEL}\n{row['notes']}"
        tgt.execute(
            "UPDATE sessions SET description = ? WHERE id = ?",
            (merged, row["session_id"]),
        )
        summary.inserted += 1
    return summary


def _recompute_session_message_counts(
    tgt: sqlite3.Connection,
) -> None:
    """Backfill ``sessions.message_count`` from the migrated ``messages``.

    The sessions and messages migrations run as separate passes so the
    FK from ``messages.session_id`` to ``sessions.id`` can resolve at
    insert time even with ``defer_foreign_keys = ON`` (we never depend
    on the deferral for this particular FK; the deferral only handles
    the ``sessions ↔ checklist_items`` cycle). At the point the
    sessions pass runs, ``messages`` is empty in the target, so a
    subquery COUNT(*) would always return zero. This pass updates the
    counter once the messages pass has populated the table.

    Idempotent: a re-run computes the same counts against the same
    rows, so ``UPDATE`` is a no-op (writes the same value).
    """
    tgt.execute(
        "UPDATE sessions SET message_count = "
        "(SELECT COUNT(*) FROM messages WHERE messages.session_id = sessions.id)"
    )


def _count_dropped_tables(
    src: sqlite3.Connection,
) -> list[tuple[str, int]]:
    """Source-side row counts for tables that have no v1 home."""
    counts: list[tuple[str, int]] = []
    for name in DROPPED_V0_17_TABLES:
        present = src.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        if present is None:
            counts.append((name, 0))
            continue
        row = src.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()
        counts.append((name, int(row["c"])))
    return counts


# ---------------------------------------------------------------------------
# Top-level migrate()
# ---------------------------------------------------------------------------


def migrate(
    *,
    source_path: Path,
    target_path: Path,
    dry_run: bool,
) -> MigrationSummary:
    """Run the full migration. Returns a populated :class:`MigrationSummary`."""
    summary = MigrationSummary(source_path=source_path, target_path=target_path, dry_run=dry_run)
    src = _open_source_readonly(source_path)
    try:
        tgt = _open_target(target_path)
        try:
            _apply_v1_schema(tgt)
            tgt.execute("PRAGMA foreign_keys = ON")
            tgt.execute("BEGIN IMMEDIATE")
            # ``sessions.checklist_item_id`` and
            # ``checklist_items.checklist_id`` form a circular FK pair;
            # ``defer_foreign_keys`` postpones enforcement until COMMIT
            # so the per-table inserts can run in any order without a
            # transient violation. Per SQLite docs, this pragma applies
            # for the duration of the current transaction only and
            # works regardless of the DEFERRABLE clause on the FK.
            tgt.execute("PRAGMA defer_foreign_keys = ON")
            try:
                summary.tables.append(_migrate_tags(src, tgt))
                summary.tables.append(_migrate_sessions(src, tgt))
                summary.tables.append(_migrate_session_tags(src, tgt))
                summary.tables.append(_migrate_tag_memories(src, tgt))
                summary.tables.append(_migrate_checklist_items(src, tgt))
                summary.tables.append(_migrate_messages(src, tgt))
                summary.tables.append(_migrate_checkpoints(src, tgt))
                summary.tables.append(_migrate_session_templates(src, tgt))
                summary.tables.append(_migrate_auto_driver_runs(src, tgt))
                summary.tables.append(_apply_checklist_notes_to_descriptions(src, tgt))
                _recompute_session_message_counts(tgt)
                summary.dropped_tables = _count_dropped_tables(src)
                if dry_run:
                    tgt.execute("ROLLBACK")
                else:
                    tgt.execute("COMMIT")
            except Exception:
                tgt.execute("ROLLBACK")
                raise
        finally:
            tgt.close()
    finally:
        src.close()
    return summary


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate_v0_17_to_v0_18",
        description=(
            "Migrate a v0.17.x Bearings DB to the v0.18 (v1 rebuild) schema. "
            "Source is opened read-only; target is created if missing. "
            "All writes happen inside a single transaction so a failed run "
            "leaves the target unchanged."
        ),
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_PATH,
        help=(f"v0.17.x DB path (default: {DEFAULT_SOURCE_PATH})"),
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET_PATH,
        help=(f"v1 DB path; created if missing (default: {DEFAULT_TARGET_PATH})"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Apply transformations inside a transaction, then ROLLBACK. "
            "Summary still reflects what would land. Re-runs are idempotent."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="DEBUG-level logging for per-row decisions.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint. Returns the process exit code."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )
    try:
        summary = migrate(
            source_path=args.source,
            target_path=args.target,
            dry_run=args.dry_run,
        )
    except MigrationError as exc:
        LOG.error("Migration failed: %s", exc)
        return EXIT_FAILURE
    print(summary.render())
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
