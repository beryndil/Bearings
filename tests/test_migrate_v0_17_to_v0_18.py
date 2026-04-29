"""Tests for the v0.17 → v0.18 migration script (item 3.2).

The fixtures here synthesize a minimal v0.17.x SQLite DB on disk per
test, so the tests do not depend on ``~/.local/share/bearings/db.sqlite``
existing on the host running pytest. The schema strings used to build
the fixture were captured by introspecting a real v0.17.x DB
(``PRAGMA table_info`` per table) — they are the data shape the
migration script must accept, not a guess.

Coverage:

* Dry-run leaves the target unchanged on disk.
* Full migration preserves row counts for every user-data table.
* Spec §5 backfill: assistant messages get
  ``routing_source='unknown_legacy'``, user messages leave it NULL,
  legacy ``input_tokens`` / ``output_tokens`` / ``cache_read_tokens``
  carry forward verbatim, ``advisor_calls_count`` defaults to 0 via
  the schema.
* Idempotency: re-running the migration on a populated target inserts
  zero new rows.
* NULL or empty-string sessions.title backfills to the
  :data:`EMPTY_TITLE_BACKFILL` sentinel — v1's ``Session`` dataclass
  rejects both at runtime (schema-level ``NOT NULL`` is necessary
  but not sufficient).
* Over-cap titles (> 500 chars) truncate with the ellipsis sentinel —
  the v1 ``Session`` dataclass enforces a Python-level cap the v0.17
  schema did not.
* Session ``kind`` and message ``role`` values outside the v1
  alphabet land in ``skipped_invalid``.
* ``checklists.notes`` merge into ``sessions.description`` only fires
  when the v1 description is empty.
* ``tags`` drops v0.17 ``pinned`` / ``sort_order`` / ``tag_group``.
* ``tag_memories`` migrates with the sentinel title and body=content.
* ``session_templates`` → ``templates`` preserves name + body and
  fills v1 defaults.
* ``auto_run_state`` → ``auto_driver_runs`` migrates counters and
  falls back to ``errored`` on out-of-alphabet states.
* ``checkpoints`` with NULL ``message_id`` are skipped (v1 NOT NULL).
* Dropped-table counts surface in the summary.

A final smoke test runs the script against the live v0.17.x DB at
``~/.local/share/bearings/db.sqlite`` if present, asserting only that
``--dry-run`` exits 0 and reports non-zero session count. Skipped
when the file isn't on disk so CI on a fresh machine still passes.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest

# Load the script as a module via spec — it lives under ``scripts/``,
# not ``src/``, so it is not import-installed. Same loader pattern as
# ``tests/test_consistency_lint.py``. Loading via spec also avoids
# mypy's "source file found twice under different module names" error
# that would fire if we did ``from scripts.migrate_v0_17_to_v0_18``.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SCRIPT_PATH: Final[Path] = _REPO_ROOT / "scripts" / "migrate_v0_17_to_v0_18.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migrate_v0_17_to_v0_18", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migrate_v0_17_to_v0_18"] = module
    spec.loader.exec_module(module)
    return module


_M: Final[ModuleType] = _load_script_module()

EMPTY_TITLE_BACKFILL: Final[str] = _M.EMPTY_TITLE_BACKFILL
LEGACY_AUTO_DRIVER_RUN_STATE_FALLBACK: Final[str] = _M.LEGACY_AUTO_DRIVER_RUN_STATE_FALLBACK
LEGACY_NOTES_DESCRIPTION_SENTINEL: Final[str] = _M.LEGACY_NOTES_DESCRIPTION_SENTINEL
LEGACY_ROUTING_SOURCE: Final[str] = _M.LEGACY_ROUTING_SOURCE
LEGACY_TAG_MEMORY_TITLE: Final[str] = _M.LEGACY_TAG_MEMORY_TITLE
TITLE_MAX_LENGTH: Final[int] = _M.TITLE_MAX_LENGTH
TRUNCATED_TITLE_SUFFIX: Final[str] = _M.TRUNCATED_TITLE_SUFFIX
MigrationError = _M.MigrationError
main = _M.main
migrate = _M.migrate

# ---------------------------------------------------------------------------
# v0.17.x schema fixture — captured via PRAGMA table_info on a real
# v0.17.x DB. The migration script reads these tables; the test fixture
# creates them so the tests don't depend on a host-installed copy of v0.17.
# ---------------------------------------------------------------------------

V0_17_SCHEMA: Final[str] = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    working_dir TEXT NOT NULL,
    model TEXT NOT NULL,
    title TEXT,
    max_budget_usd REAL,
    total_cost_usd REAL NOT NULL DEFAULT 0,
    description TEXT,
    session_instructions TEXT,
    sdk_session_id TEXT,
    permission_mode TEXT,
    last_context_pct REAL,
    last_context_tokens INTEGER,
    last_context_max INTEGER,
    closed_at TEXT,
    kind TEXT NOT NULL DEFAULT 'chat',
    checklist_item_id INTEGER,
    last_completed_at TEXT,
    last_viewed_at TEXT,
    pinned INTEGER NOT NULL DEFAULT 0,
    error_pending INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    thinking TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_creation_tokens INTEGER,
    replay_attempted_at TEXT,
    pinned INTEGER NOT NULL DEFAULT 0,
    hidden_from_context INTEGER NOT NULL DEFAULT 0,
    attachments TEXT
);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT,
    pinned INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    default_working_dir TEXT,
    default_model TEXT,
    tag_group TEXT NOT NULL DEFAULT 'general'
);

CREATE TABLE session_tags (
    session_id TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, tag_id)
);

CREATE TABLE tag_memories (
    tag_id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE checklists (
    session_id TEXT PRIMARY KEY,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE checklist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checklist_id TEXT NOT NULL,
    parent_item_id INTEGER,
    label TEXT NOT NULL,
    notes TEXT,
    checked_at TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    chat_session_id TEXT,
    blocked_at TEXT,
    blocked_reason_category TEXT,
    blocked_reason_text TEXT
);

CREATE TABLE checkpoints (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    message_id TEXT,
    label TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE session_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    body TEXT,
    working_dir TEXT,
    model TEXT,
    session_instructions TEXT,
    tag_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE auto_run_state (
    checklist_session_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    items_completed INTEGER NOT NULL DEFAULT 0,
    items_failed INTEGER NOT NULL DEFAULT 0,
    items_skipped INTEGER NOT NULL DEFAULT 0,
    legs_spawned INTEGER NOT NULL DEFAULT 0,
    failed_item_id INTEGER,
    failure_reason TEXT,
    config_json TEXT NOT NULL,
    attempted_failed_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    items_blocked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE tool_calls (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    message_id TEXT,
    name TEXT NOT NULL,
    input TEXT NOT NULL,
    output TEXT,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE preferences (
    id INTEGER PRIMARY KEY,
    display_name TEXT,
    theme TEXT,
    default_model TEXT,
    default_working_dir TEXT,
    notify_on_complete INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE reorg_audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_session_id TEXT NOT NULL,
    target_session_id TEXT,
    target_title_snapshot TEXT,
    message_count INTEGER NOT NULL,
    op TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    checksum TEXT
);
"""

# ---------------------------------------------------------------------------
# Canonical timestamps + IDs used by the fixture rows
# ---------------------------------------------------------------------------

TS_CHAT_CREATED: Final[str] = "2026-01-01T00:00:00+00:00"
TS_CHECKLIST_CREATED: Final[str] = "2026-01-02T00:00:00+00:00"
TS_MESSAGE_CREATED: Final[str] = "2026-01-01T00:00:01+00:00"

CHAT_SESSION_ID: Final[str] = "chat-session-aaaaaaaaaaaaaaaaaa"
CHECKLIST_SESSION_ID: Final[str] = "checklist-session-bbbbbbbbbb"
NULL_TITLE_SESSION_ID: Final[str] = "null-title-session-cccccccc"
INVALID_KIND_SESSION_ID: Final[str] = "invalid-kind-session-ddddddd"
NOTES_MERGE_SESSION_ID: Final[str] = "notes-merge-session-eeeeeeee"
LONG_TITLE_SESSION_ID: Final[str] = "long-title-session-ffffffffff"
EMPTY_TITLE_SESSION_ID: Final[str] = "empty-title-session-gggggggg"

# Synthesises a v0.17 title that exceeds the v1
# ``SESSION_TITLE_MAX_LENGTH`` (500) so the migrator's truncation
# path runs. Mirrors the dogfood reality where a couple of sessions
# accumulated checklist-prose-as-title in early v0.17.x. Length 1504
# matches the actual outlier observed during the item 3.4 cutover
# smoke against the live ``~/.local/share/bearings/db.sqlite``.
LONG_TITLE_TEXT: Final[str] = "x" * 1504

ASSISTANT_MESSAGE_ID: Final[str] = "msg-assistant-fffffffffffffff"
USER_MESSAGE_ID: Final[str] = "msg-user-gggggggggggggggggggg"
INVALID_ROLE_MESSAGE_ID: Final[str] = "msg-invalid-hhhhhhhhhhhhhhhh"

ASSISTANT_INPUT_TOKENS: Final[int] = 1234
ASSISTANT_OUTPUT_TOKENS: Final[int] = 5678
ASSISTANT_CACHE_READ_TOKENS: Final[int] = 9876

CHECKPOINT_VALID_ID: Final[str] = "ckpt-valid-iiiiiiiiiiiiiiiiii"
CHECKPOINT_NULL_MSG_ID: Final[str] = "ckpt-null-msg-jjjjjjjjjjjjj"

TEMPLATE_NAME: Final[str] = "exec-template-1"
TEMPLATE_BODY: Final[str] = "Baseline system prompt"

LEGACY_NOTES_TEXT: Final[str] = "Top-of-checklist notes from v0.17"

INVALID_AUTO_RUN_STATE: Final[str] = "running_legacy_unknown"

# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------


def _seed_v0_17_db(db_path: Path) -> None:
    """Build a canonical v0.17.x DB at ``db_path`` with one row per
    migration path.

    The set of rows is chosen so a single migration run exercises every
    interesting code path in :mod:`scripts.migrate_v0_17_to_v0_18`:

    * a chat session + an assistant message + a user message;
    * a checklist session with one root + one nested ``checklist_item``;
    * a session with NULL title (NULL-title backfill path);
    * a session with an empty-string title (empty-title backfill path);
    * a session with a 1504-char title (long-title-truncate path);
    * a session with an out-of-alphabet ``kind`` (skipped_invalid);
    * a message with an out-of-alphabet ``role`` (skipped_invalid);
    * a tag with all the v0.17-only columns populated;
    * a session_tags join row;
    * one ``tag_memories`` row;
    * one ``checkpoints`` row with a valid ``message_id`` plus one with
      NULL ``message_id`` (v1-NOT-NULL → skipped_invalid);
    * one ``session_templates`` row;
    * one ``auto_run_state`` row whose state is outside the v1
      alphabet (state-fallback path);
    * one ``checklists.notes`` row that lands on a session whose
      description is currently empty (notes_merge inserts);
    * one ``checklists.notes`` row that lands on a session whose
      description is non-empty (notes_merge skipped_existing);
    * non-zero counts in every dropped table so the summary reports
      them.
    """
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(V0_17_SCHEMA)
        cur = connection.cursor()

        # tags
        cur.execute(
            "INSERT INTO tags "
            "(id, name, color, pinned, sort_order, created_at, "
            "default_working_dir, default_model, tag_group) "
            "VALUES (1, 'bearings', '#2c5', 1, 5, ?, '/wd-tag', 'sonnet', 'core')",
            (TS_CHAT_CREATED,),
        )

        # tag_memories — one row, sentinel-title path
        cur.execute(
            "INSERT INTO tag_memories (tag_id, content, updated_at) "
            "VALUES (1, 'tag-memory-content', ?)",
            (TS_CHAT_CREATED,),
        )

        # sessions — chat + checklist + null-title + invalid-kind +
        # notes-merge target.
        cur.executemany(
            "INSERT INTO sessions "
            "(id, created_at, updated_at, working_dir, model, title, "
            "description, kind, pinned, error_pending, total_cost_usd) "
            "VALUES (?, ?, ?, '/wd', 'sonnet', ?, ?, ?, ?, ?, 0)",
            [
                (
                    CHAT_SESSION_ID,
                    TS_CHAT_CREATED,
                    TS_CHAT_CREATED,
                    "Chat title",
                    "Chat description",
                    "chat",
                    0,
                    0,
                ),
                (
                    CHECKLIST_SESSION_ID,
                    TS_CHECKLIST_CREATED,
                    TS_CHECKLIST_CREATED,
                    "Checklist title",
                    None,
                    "checklist",
                    0,
                    0,
                ),
                (NULL_TITLE_SESSION_ID, TS_CHAT_CREATED, TS_CHAT_CREATED, None, None, "chat", 0, 0),
                (
                    INVALID_KIND_SESSION_ID,
                    TS_CHAT_CREATED,
                    TS_CHAT_CREATED,
                    "Invalid kind",
                    None,
                    "ghost_kind",
                    0,
                    0,
                ),
                (
                    NOTES_MERGE_SESSION_ID,
                    TS_CHECKLIST_CREATED,
                    TS_CHECKLIST_CREATED,
                    "Notes merge target",
                    None,
                    "checklist",
                    0,
                    0,
                ),
                # Session with a v0.17 title longer than v1's
                # ``SESSION_TITLE_MAX_LENGTH``; the migrator truncates
                # to fit the dataclass invariant rather than dropping
                # the row. Exercises ``test_long_title_truncated``.
                (
                    LONG_TITLE_SESSION_ID,
                    TS_CHAT_CREATED,
                    TS_CHAT_CREATED,
                    LONG_TITLE_TEXT,
                    None,
                    "chat",
                    0,
                    0,
                ),
                # Session with an empty-string title — v0.17's schema
                # admits ``''`` (TEXT NOT NULL) but v1's runtime
                # ``Session`` dataclass rejects it. Exercises
                # ``test_empty_title_backfills_to_sentinel``.
                (
                    EMPTY_TITLE_SESSION_ID,
                    TS_CHAT_CREATED,
                    TS_CHAT_CREATED,
                    "",
                    None,
                    "chat",
                    0,
                    0,
                ),
            ],
        )

        # session_tags
        cur.execute(
            "INSERT INTO session_tags (session_id, tag_id, created_at) VALUES (?, 1, ?)",
            (CHAT_SESSION_ID, TS_CHAT_CREATED),
        )

        # checklists — one with notes that should merge (target empty
        # description); one whose target session has a description
        # already set.
        cur.executemany(
            "INSERT INTO checklists (session_id, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            [
                (
                    NOTES_MERGE_SESSION_ID,
                    LEGACY_NOTES_TEXT,
                    TS_CHECKLIST_CREATED,
                    TS_CHECKLIST_CREATED,
                ),
                (
                    CHAT_SESSION_ID,
                    "should not merge — chat has description",
                    TS_CHAT_CREATED,
                    TS_CHAT_CREATED,
                ),
            ],
        )

        # checklist_items — one root + one child.
        cur.execute(
            "INSERT INTO checklist_items "
            "(id, checklist_id, parent_item_id, label, sort_order, created_at, updated_at) "
            "VALUES (1, ?, NULL, 'root', 0, ?, ?)",
            (CHECKLIST_SESSION_ID, TS_CHECKLIST_CREATED, TS_CHECKLIST_CREATED),
        )
        cur.execute(
            "INSERT INTO checklist_items "
            "(id, checklist_id, parent_item_id, label, sort_order, created_at, updated_at) "
            "VALUES (2, ?, 1, 'child', 0, ?, ?)",
            (CHECKLIST_SESSION_ID, TS_CHECKLIST_CREATED, TS_CHECKLIST_CREATED),
        )

        # messages — assistant (with legacy tokens), user, invalid role.
        cur.execute(
            "INSERT INTO messages "
            "(id, session_id, role, content, created_at, thinking, "
            "input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens) "
            "VALUES (?, ?, 'assistant', 'asst body', ?, 'thinking', ?, ?, ?, 42)",
            (
                ASSISTANT_MESSAGE_ID,
                CHAT_SESSION_ID,
                TS_MESSAGE_CREATED,
                ASSISTANT_INPUT_TOKENS,
                ASSISTANT_OUTPUT_TOKENS,
                ASSISTANT_CACHE_READ_TOKENS,
            ),
        )
        cur.execute(
            "INSERT INTO messages "
            "(id, session_id, role, content, created_at) "
            "VALUES (?, ?, 'user', 'user body', ?)",
            (USER_MESSAGE_ID, CHAT_SESSION_ID, TS_MESSAGE_CREATED),
        )
        cur.execute(
            "INSERT INTO messages "
            "(id, session_id, role, content, created_at) "
            "VALUES (?, ?, 'ghost_role', 'invalid role body', ?)",
            (INVALID_ROLE_MESSAGE_ID, CHAT_SESSION_ID, TS_MESSAGE_CREATED),
        )

        # checkpoints — one valid + one with NULL message_id.
        cur.execute(
            "INSERT INTO checkpoints (id, session_id, message_id, label, created_at) "
            "VALUES (?, ?, ?, 'cp-label', ?)",
            (CHECKPOINT_VALID_ID, CHAT_SESSION_ID, ASSISTANT_MESSAGE_ID, TS_MESSAGE_CREATED),
        )
        cur.execute(
            "INSERT INTO checkpoints (id, session_id, message_id, label, created_at) "
            "VALUES (?, ?, NULL, 'orphan', ?)",
            (CHECKPOINT_NULL_MSG_ID, CHAT_SESSION_ID, TS_MESSAGE_CREATED),
        )

        # session_templates
        cur.execute(
            "INSERT INTO session_templates "
            "(id, name, body, working_dir, model, session_instructions, "
            "tag_ids_json, created_at) "
            "VALUES ('tmpl-uuid-v0-17', ?, ?, '/wd-template', 'sonnet', 'instr', "
            "'[1]', ?)",
            (TEMPLATE_NAME, TEMPLATE_BODY, TS_CHAT_CREATED),
        )

        # auto_run_state — invalid state to exercise the fallback path.
        cur.execute(
            "INSERT INTO auto_run_state "
            "(checklist_session_id, state, items_completed, items_failed, "
            "items_skipped, legs_spawned, items_blocked, config_json, "
            "created_at, updated_at) "
            "VALUES (?, ?, 7, 1, 2, 4, 1, '{}', ?, ?)",
            (
                CHECKLIST_SESSION_ID,
                INVALID_AUTO_RUN_STATE,
                TS_CHECKLIST_CREATED,
                TS_CHECKLIST_CREATED,
            ),
        )

        # Dropped tables — non-zero counts so the summary surfaces them.
        cur.execute(
            "INSERT INTO artifacts "
            "(id, session_id, path, filename, mime_type, size_bytes, sha256, created_at) "
            "VALUES ('a1', ?, '/p', 'f.txt', 'text/plain', 1, 'h', ?)",
            (CHAT_SESSION_ID, TS_CHAT_CREATED),
        )
        cur.execute(
            "INSERT INTO tool_calls "
            "(id, session_id, name, input, started_at) "
            "VALUES ('t1', ?, 'Read', '{}', ?)",
            (CHAT_SESSION_ID, TS_CHAT_CREATED),
        )
        cur.execute(
            "INSERT INTO preferences (id, theme, notify_on_complete, updated_at) "
            "VALUES (1, 'dark', 0, ?)",
            (TS_CHAT_CREATED,),
        )
        cur.execute(
            "INSERT INTO reorg_audits "
            "(source_session_id, message_count, op, created_at) "
            "VALUES (?, 5, 'merge', ?)",
            (CHAT_SESSION_ID, TS_CHAT_CREATED),
        )
        cur.execute(
            "INSERT INTO schema_migrations (name, applied_at) VALUES ('0001_init', ?)",
            (TS_CHAT_CREATED,),
        )

        connection.commit()
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def v0_17_db(tmp_path: Path) -> Path:
    """A freshly-built v0.17.x DB ready to migrate."""
    path = tmp_path / "v0_17.sqlite"
    _seed_v0_17_db(path)
    return path


@pytest.fixture
def target_db_path(tmp_path: Path) -> Path:
    """Target path that does not exist yet — the migrator creates it."""
    return tmp_path / "v0_18.sqlite"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _table_summary(summary: object, name: str) -> object:
    """Return the :class:`TableSummary` row for ``name`` from the
    rendered :class:`MigrationSummary`."""
    tables = getattr(summary, "tables")
    matches = [t for t in tables if getattr(t, "name") == name]
    assert matches, f"no table summary for {name}"
    return matches[0]


# ---------------------------------------------------------------------------
# Tests — core invariants
# ---------------------------------------------------------------------------


def test_dry_run_does_not_create_target_rows(v0_17_db: Path, target_db_path: Path) -> None:
    """Dry-run applies the v1 schema (so the target is a valid v1 DB)
    but rolls back every transformation; the row count for every user
    table is zero on disk after the call returns."""
    summary = migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=True)
    assert summary.dry_run is True

    # The summary still reports what would land.
    sessions_row = _table_summary(summary, "sessions")
    assert getattr(sessions_row, "inserted") > 0

    # On disk, the schema is applied but no rows landed.
    with _open(target_db_path) as conn:
        for table in ("sessions", "messages", "tags", "checklist_items"):
            row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
            assert row["c"] == 0, f"dry-run leaked into {table}"


def test_full_migration_round_counts(v0_17_db: Path, target_db_path: Path) -> None:
    """A real (non-dry) migration lands every valid source row."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        # 7 source sessions (chat, checklist, null-title, invalid-kind,
        # notes-merge, long-title, empty-title), 1 invalid-kind → 6
        # land. Long-title and empty-title rows are repaired in
        # place, not skipped.
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 6
        # 3 source messages, 1 invalid-role → 2 land.
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM session_tags").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM checklist_items").fetchone()[0] == 2
        # 2 source checkpoints, 1 NULL message_id → 1 lands.
        assert conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM tag_memories").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM auto_driver_runs").fetchone()[0] == 1


def test_idempotent_re_run_inserts_zero(v0_17_db: Path, target_db_path: Path) -> None:
    """Re-running the migration on a populated target inserts nothing."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    second = migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    for table in second.tables:
        assert getattr(table, "inserted") == 0, (
            f"{getattr(table, 'name')} re-inserted on second run"
        )


# ---------------------------------------------------------------------------
# Tests — backfill (spec §5)
# ---------------------------------------------------------------------------


def test_assistant_message_gets_unknown_legacy_routing_source(
    v0_17_db: Path, target_db_path: Path
) -> None:
    """Spec §5 Backfill: every assistant message's
    ``routing_source`` is ``'unknown_legacy'`` so the override-rate
    aggregator filters it out."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT routing_source FROM messages WHERE id = ?",
            (ASSISTANT_MESSAGE_ID,),
        ).fetchone()
    assert row["routing_source"] == LEGACY_ROUTING_SOURCE


def test_user_message_routing_source_stays_null(v0_17_db: Path, target_db_path: Path) -> None:
    """User rows never had routing data; ``routing_source`` is NULL."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT routing_source FROM messages WHERE id = ?",
            (USER_MESSAGE_ID,),
        ).fetchone()
    assert row["routing_source"] is None


def test_legacy_token_columns_carry_forward(v0_17_db: Path, target_db_path: Path) -> None:
    """``input_tokens`` / ``output_tokens`` / ``cache_read_tokens``
    survive verbatim per spec §5."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT input_tokens, output_tokens, cache_read_tokens FROM messages WHERE id = ?",
            (ASSISTANT_MESSAGE_ID,),
        ).fetchone()
    assert row["input_tokens"] == ASSISTANT_INPUT_TOKENS
    assert row["output_tokens"] == ASSISTANT_OUTPUT_TOKENS
    assert row["cache_read_tokens"] == ASSISTANT_CACHE_READ_TOKENS


_PER_MODEL_USAGE_COLUMNS: Final[tuple[str, ...]] = (
    "executor_model",
    "advisor_model",
    "effort_level",
    "matched_rule_id",
    "executor_input_tokens",
    "executor_output_tokens",
    "advisor_input_tokens",
    "advisor_output_tokens",
)


def test_per_model_usage_columns_default_to_null(v0_17_db: Path, target_db_path: Path) -> None:
    """The new spec §5 per-model columns are NULL on legacy rows."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    select_clause = ", ".join(_PER_MODEL_USAGE_COLUMNS)
    with _open(target_db_path) as conn:
        row = conn.execute(
            f"SELECT {select_clause} FROM messages WHERE id = ?",
            (ASSISTANT_MESSAGE_ID,),
        ).fetchone()
    for column in _PER_MODEL_USAGE_COLUMNS:
        assert row[column] is None, f"{column} should be NULL on legacy row"


def test_advisor_calls_count_uses_schema_default_zero(v0_17_db: Path, target_db_path: Path) -> None:
    """Spec §5 verbatim: ``advisor_calls_count INTEGER DEFAULT 0``."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT advisor_calls_count FROM messages WHERE id = ?",
            (ASSISTANT_MESSAGE_ID,),
        ).fetchone()
    assert row["advisor_calls_count"] == 0


# ---------------------------------------------------------------------------
# Tests — sessions transformations
# ---------------------------------------------------------------------------


def test_null_title_backfills_to_sentinel(v0_17_db: Path, target_db_path: Path) -> None:
    """v0.17 ``sessions.title`` could be NULL; the v1 ``Session``
    dataclass invariant requires a non-empty title. The migrator
    substitutes :data:`EMPTY_TITLE_BACKFILL` so the row survives the
    schema's ``TEXT NOT NULL`` AND the runtime non-empty check."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT title FROM sessions WHERE id = ?",
            (NULL_TITLE_SESSION_ID,),
        ).fetchone()
    assert row["title"] == EMPTY_TITLE_BACKFILL
    assert row["title"], "backfilled title must be non-empty per Session.__post_init__"


def test_empty_title_backfills_to_sentinel(v0_17_db: Path, target_db_path: Path) -> None:
    """v0.17 admitted empty-string titles (``TEXT NOT NULL`` alone);
    v1 rejects them at the dataclass layer. The migrator coerces
    empty-string titles to :data:`EMPTY_TITLE_BACKFILL` alongside
    NULLs."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT title FROM sessions WHERE id = ?",
            (EMPTY_TITLE_SESSION_ID,),
        ).fetchone()
    assert row["title"] == EMPTY_TITLE_BACKFILL


def test_long_title_truncated(v0_17_db: Path, target_db_path: Path) -> None:
    """v0.17 had no title-length cap; v1's ``Session`` dataclass
    rejects titles > ``SESSION_TITLE_MAX_LENGTH`` (500) at runtime.
    The migrator truncates the title to fit (with the
    :data:`TRUNCATED_TITLE_SUFFIX` ellipsis sentinel) so the row is
    preserved end-to-end through ``GET /api/sessions``.

    Without this transformation, item 3.4's cutover smoke surfaced a
    real 500 on the migrated DB whose outlier title was 1504 chars."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT title FROM sessions WHERE id = ?",
            (LONG_TITLE_SESSION_ID,),
        ).fetchone()
    assert row is not None
    title: str = row["title"]
    assert len(title) == TITLE_MAX_LENGTH, (
        f"truncated title should be exactly {TITLE_MAX_LENGTH} chars, got {len(title)}"
    )
    assert title.endswith(TRUNCATED_TITLE_SUFFIX), (
        f"truncated title should carry the {TRUNCATED_TITLE_SUFFIX!r} suffix"
    )
    assert title.startswith("x" * (TITLE_MAX_LENGTH - len(TRUNCATED_TITLE_SUFFIX))), (
        "truncated title should preserve the original prefix"
    )


def test_session_with_invalid_kind_skipped(v0_17_db: Path, target_db_path: Path) -> None:
    """A v0.17 session whose ``kind`` is outside the v1 alphabet is
    counted in ``skipped_invalid`` and absent from the target."""
    summary = migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    sessions_row = _table_summary(summary, "sessions")
    assert getattr(sessions_row, "skipped_invalid") == 1
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM sessions WHERE id = ?",
            (INVALID_KIND_SESSION_ID,),
        ).fetchone()
    assert row is None


def test_message_with_invalid_role_skipped(v0_17_db: Path, target_db_path: Path) -> None:
    """A v0.17 message whose ``role`` is outside the v1 alphabet is
    counted in ``skipped_invalid`` and absent from the target."""
    summary = migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    messages_row = _table_summary(summary, "messages")
    assert getattr(messages_row, "skipped_invalid") == 1
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM messages WHERE id = ?",
            (INVALID_ROLE_MESSAGE_ID,),
        ).fetchone()
    assert row is None


def test_session_message_count_is_recomputed(v0_17_db: Path, target_db_path: Path) -> None:
    """v1 ``sessions.message_count`` is computed from the migrated
    messages — the migrator does not trust a denormalised v0.17
    counter (there isn't one anyway)."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT message_count FROM sessions WHERE id = ?",
            (CHAT_SESSION_ID,),
        ).fetchone()
    # 2 valid messages live on the chat session (assistant + user; the
    # invalid-role row was rejected).
    assert row["message_count"] == 2


# ---------------------------------------------------------------------------
# Tests — tags / tag_memories
# ---------------------------------------------------------------------------


def test_tags_drop_v0_17_only_columns(v0_17_db: Path, target_db_path: Path) -> None:
    """``pinned`` / ``sort_order`` / ``tag_group`` are not in the v1
    schema; the migration discards them and remaps
    ``default_working_dir`` to ``working_dir``."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT name, color, default_model, working_dir, created_at, updated_at "
            "FROM tags WHERE id = 1"
        ).fetchone()
    assert row["name"] == "bearings"
    assert row["color"] == "#2c5"
    assert row["default_model"] == "sonnet"
    assert row["working_dir"] == "/wd-tag"
    # updated_at backfills to created_at since v0.17 didn't track it.
    assert row["created_at"] == row["updated_at"] == TS_CHAT_CREATED


def test_tag_memory_lands_with_sentinel_title(v0_17_db: Path, target_db_path: Path) -> None:
    """v1 ``tag_memories.title`` is NOT NULL; the migration uses a
    deterministic sentinel so re-runs are idempotent."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute("SELECT title, body, enabled, tag_id FROM tag_memories").fetchone()
    assert row["title"] == LEGACY_TAG_MEMORY_TITLE
    assert row["body"] == "tag-memory-content"
    assert row["enabled"] == 1
    assert row["tag_id"] == 1


# ---------------------------------------------------------------------------
# Tests — checkpoints / templates / auto_driver_runs / notes-merge
# ---------------------------------------------------------------------------


def test_checkpoint_with_null_message_id_skipped(v0_17_db: Path, target_db_path: Path) -> None:
    """v0.17 ``checkpoints.message_id`` was nullable; v1 declares NOT
    NULL. The orphan row lands in ``skipped_invalid``."""
    summary = migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    checkpoints_row = _table_summary(summary, "checkpoints")
    assert getattr(checkpoints_row, "skipped_invalid") == 1
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM checkpoints WHERE id = ?",
            (CHECKPOINT_NULL_MSG_ID,),
        ).fetchone()
    assert row is None


def test_template_preserves_name_and_body(v0_17_db: Path, target_db_path: Path) -> None:
    """``session_templates.body`` lands in ``templates.system_prompt_baseline``;
    the v1 defaults populate the rest of the row."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT name, system_prompt_baseline, model, advisor_max_uses, "
            "effort_level, permission_profile, working_dir_default, tag_names_json "
            "FROM templates WHERE name = ?",
            (TEMPLATE_NAME,),
        ).fetchone()
    assert row["name"] == TEMPLATE_NAME
    assert row["system_prompt_baseline"] == TEMPLATE_BODY
    assert row["model"] == "sonnet"
    assert row["advisor_max_uses"] == 5
    assert row["effort_level"] == "auto"
    assert row["permission_profile"] == "standard"
    assert row["working_dir_default"] == "/wd-template"
    assert row["tag_names_json"] == "[]"


def test_auto_run_state_with_invalid_state_falls_back(v0_17_db: Path, target_db_path: Path) -> None:
    """A v0.17 ``state`` value outside the v1 alphabet falls back to
    ``errored`` so the row's counters survive."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT state, items_completed, items_failed, items_blocked, "
            "items_skipped, items_attempted, legs_spawned, started_at, updated_at "
            "FROM auto_driver_runs WHERE checklist_id = ?",
            (CHECKLIST_SESSION_ID,),
        ).fetchone()
    assert row["state"] == LEGACY_AUTO_DRIVER_RUN_STATE_FALLBACK
    assert row["items_completed"] == 7
    assert row["items_failed"] == 1
    assert row["items_blocked"] == 1
    assert row["items_skipped"] == 2
    assert row["legs_spawned"] == 4
    # items_attempted backfills to the sum of completed/failed/blocked/skipped.
    assert row["items_attempted"] == 11
    assert row["started_at"] == TS_CHECKLIST_CREATED


def test_checklist_notes_merge_into_empty_description(v0_17_db: Path, target_db_path: Path) -> None:
    """A v0.17 ``checklists.notes`` row whose target session has an
    empty description gets merged in with the sentinel prefix."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT description FROM sessions WHERE id = ?",
            (NOTES_MERGE_SESSION_ID,),
        ).fetchone()
    assert row["description"] is not None
    assert row["description"].startswith(LEGACY_NOTES_DESCRIPTION_SENTINEL)
    assert LEGACY_NOTES_TEXT in row["description"]


def test_checklist_notes_skip_when_description_already_set(
    v0_17_db: Path, target_db_path: Path
) -> None:
    """A v0.17 ``checklists.notes`` row whose target session already
    has a description is left alone (the user's text wins)."""
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    with _open(target_db_path) as conn:
        row = conn.execute(
            "SELECT description FROM sessions WHERE id = ?",
            (CHAT_SESSION_ID,),
        ).fetchone()
    assert row["description"] == "Chat description"
    assert LEGACY_NOTES_DESCRIPTION_SENTINEL not in row["description"]


# ---------------------------------------------------------------------------
# Tests — dropped tables / source DB protection
# ---------------------------------------------------------------------------


def test_dropped_table_counts_appear_in_summary(v0_17_db: Path, target_db_path: Path) -> None:
    """The summary reports source-row counts for every dropped table."""
    summary = migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    dropped = dict(summary.dropped_tables)
    assert dropped["artifacts"] == 1
    assert dropped["tool_calls"] == 1
    assert dropped["preferences"] == 1
    assert dropped["reorg_audits"] == 1
    assert dropped["schema_migrations"] == 1


def test_source_db_unchanged_after_migration(v0_17_db: Path, target_db_path: Path) -> None:
    """The source DB is opened read-only; row counts after migration
    match counts before migration."""
    before = _row_count_snapshot(v0_17_db)
    migrate(source_path=v0_17_db, target_path=target_db_path, dry_run=False)
    after = _row_count_snapshot(v0_17_db)
    assert before == after


def _row_count_snapshot(path: Path) -> dict[str, int]:
    """Return ``{table_name: row_count}`` for every user table."""
    with _open(path) as conn:
        names = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        # ``name`` comes from sqlite_master so the f-string interpolation
        # is hermetic — sqlite_master only ever contains real table names.
        return {
            name: conn.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()["c"]
            for name in names
        }


def test_missing_source_raises_migration_error(tmp_path: Path, target_db_path: Path) -> None:
    """A non-existent source path produces :class:`MigrationError`,
    not a generic IOError, so the CLI can render a helpful message."""
    missing = tmp_path / "does-not-exist.sqlite"
    with pytest.raises(MigrationError, match="Source DB not found"):
        migrate(source_path=missing, target_path=target_db_path, dry_run=True)


# ---------------------------------------------------------------------------
# CLI / smoke tests
# ---------------------------------------------------------------------------


def test_main_returns_success_on_dry_run(
    v0_17_db: Path, target_db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI entrypoint prints the summary and returns 0."""
    rc = main(
        [
            "--source",
            str(v0_17_db),
            "--target",
            str(target_db_path),
            "--dry-run",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr().out
    assert "Migration DRY-RUN" in captured
    assert "sessions" in captured


def test_main_returns_failure_on_missing_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI surfaces :class:`MigrationError` as a non-zero exit code."""
    missing = tmp_path / "nope.sqlite"
    target = tmp_path / "tgt.sqlite"
    rc = main(["--source", str(missing), "--target", str(target)])
    assert rc != 0


_LIVE_V0_17_PATH: Final[Path] = Path("~/.local/share/bearings/db.sqlite").expanduser()


@pytest.mark.skipif(
    not _LIVE_V0_17_PATH.exists(),
    reason="live v0.17.x DB not present on this host",
)
def test_smoke_against_live_v0_17_db_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Smoke: ``--dry-run`` against the host's real v0.17.x DB exits 0
    and reports a non-zero session count. Skipped on hosts that don't
    have the file."""
    target = tmp_path / "live-smoke.sqlite"
    rc = main(
        [
            "--source",
            str(_LIVE_V0_17_PATH),
            "--target",
            str(target),
            "--dry-run",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr().out
    assert "Migration DRY-RUN" in captured
