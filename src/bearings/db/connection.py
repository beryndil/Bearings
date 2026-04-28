"""aiosqlite connection bootstrap for the Bearings v1 database.

Two pieces of public surface:

* :func:`get_connection_factory` returns a no-argument callable each
  invocation of which opens a fresh ``aiosqlite.Connection`` at the same
  on-disk path. Callers use it as ``async with factory() as conn:`` per the
  hand-verify recipe in the item-0.4 instructions; the factory itself does
  no I/O until called.
* :func:`load_schema` applies the canonical DDL from ``schema.sql`` to an
  open connection. The DDL is itself idempotent (every ``CREATE TABLE`` and
  every ``CREATE INDEX`` uses ``IF NOT EXISTS``; every seeded
  ``system_routing_rules`` row is wrapped in ``INSERT OR IGNORE`` against a
  partial unique index on ``(priority) WHERE seeded = 1``). Calling
  ``load_schema`` against a freshly-opened connection on an existing DB is a
  no-op.

Foreign-key enforcement is opt-in per connection in SQLite — the bootstrap
issues ``PRAGMA foreign_keys = ON`` before applying the DDL so that the
``ON DELETE`` clauses declared in ``schema.sql`` actually fire. Downstream
query modules that open their own connection must repeat the pragma; the
schema-test suite verifies this contract.

References:

* ``docs/architecture-v1.md`` §1.1.3 — bootstrap responsibility lives in
  this module; ``aiosqlite`` is the async driver pinned at the project
  level.
* ``docs/model-routing-v1-spec.md`` §3 — seven default ``system_routing_rules``
  rows are seeded on first apply, idempotent on re-init.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

import aiosqlite

# Resolved at import time so a renamed/relocated schema.sql produces an
# ImportError at module load rather than a runtime failure deep inside the
# first ``load_schema`` call.
SCHEMA_PATH: Final[Path] = Path(__file__).parent / "schema.sql"


def get_connection_factory(
    database_path: Path,
) -> Callable[[], aiosqlite.Connection]:
    """Return a no-argument factory that opens connections to ``database_path``.

    The returned ``aiosqlite.Connection`` is itself an async context manager;
    callers use ``async with factory() as conn:`` to scope the lifetime. The
    factory does not load the schema — the caller invokes :func:`load_schema`
    explicitly inside the context, so test code can open a connection
    without mutating disk state.
    """

    def _factory() -> aiosqlite.Connection:
        return aiosqlite.connect(database_path)

    return _factory


async def load_schema(connection: aiosqlite.Connection) -> None:
    """Apply ``schema.sql`` to ``connection`` and seed default system rules.

    Idempotent on re-init: every ``CREATE TABLE`` / ``CREATE INDEX`` in the
    DDL uses ``IF NOT EXISTS``, and the seven default
    ``system_routing_rules`` rows use ``INSERT OR IGNORE`` against the
    partial unique index ``idx_system_routing_rules_seeded_priority``.

    Foreign keys are enabled on this connection before the DDL runs (the
    pragma is per-connection in SQLite). Downstream callers that open their
    own connection are responsible for repeating ``PRAGMA foreign_keys =
    ON``; this contract is verified by ``tests/test_db_schema.py``.
    """
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    await connection.execute("PRAGMA foreign_keys = ON")
    await connection.executescript(schema_sql)
    await connection.commit()
