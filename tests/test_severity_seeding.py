"""Tests for T3-01 severity tag auto-seeding in ``db/connection.py``.

Verifies:

1. A fresh DB seeded via :func:`ensure_severity_tags` produces exactly 5
   severity tags.
2. A second call is idempotent — still exactly 5 rows.
3. The seeded tags have the expected names and class.
4. No seeding occurs for names that already exist (no duplicates).

:func:`ensure_severity_tags` is intentionally *not* called by
:func:`load_schema` (to keep test DB isolation clean); it is called at
server-startup time by ``cli/serve.py:_connect_db``.

References:

* ``src/bearings/db/connection.py:ensure_severity_tags``
* ``src/bearings/db/connection.py:_SEVERITY_SEED``
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import aiosqlite
import pytest

from bearings.db import ensure_severity_tags, get_connection_factory, load_schema

# Expected names produced by the seed in sort_order order.
EXPECTED_SEVERITY_NAMES: tuple[str, ...] = (
    "Blocker",
    "Critical",
    "Medium",
    "Low",
    "QoL",
)

EXPECTED_SEVERITY_COUNT: int = len(EXPECTED_SEVERITY_NAMES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _count_severity_tags(conn: aiosqlite.Connection) -> int:
    """Return the number of rows in tags with class = 'severity'."""
    async with conn.execute("SELECT COUNT(*) FROM tags WHERE class = 'severity'") as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def _severity_tag_names(conn: aiosqlite.Connection) -> list[str]:
    """Return severity tag names ordered by sort_order, name."""
    async with conn.execute(
        "SELECT name FROM tags WHERE class = 'severity' ORDER BY sort_order ASC, name ASC"
    ) as cur:
        rows = await cur.fetchall()
    return [str(r[0]) for r in rows]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_bootstrap_seeds_exactly_five_severity_tags() -> None:
    """ensure_severity_tags on a fresh DB produces exactly 5 severity tags."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        factory = get_connection_factory(db_path)
        async with factory() as conn:
            await load_schema(conn)
            await ensure_severity_tags(conn)
            count = await _count_severity_tags(conn)
    assert count == EXPECTED_SEVERITY_COUNT


@pytest.mark.asyncio
async def test_seeded_tags_have_correct_names() -> None:
    """Seeded severity tags are named Blocker/Critical/Medium/Low/QoL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        factory = get_connection_factory(db_path)
        async with factory() as conn:
            await load_schema(conn)
            await ensure_severity_tags(conn)
            names = await _severity_tag_names(conn)
    assert names == list(EXPECTED_SEVERITY_NAMES)


@pytest.mark.asyncio
async def test_seeded_tags_have_severity_class() -> None:
    """Every seeded tag has class = 'severity'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        factory = get_connection_factory(db_path)
        async with factory() as conn:
            await load_schema(conn)
            await ensure_severity_tags(conn)
            async with conn.execute(
                "SELECT COUNT(*) FROM tags WHERE class != 'severity'"
                " AND name IN ('Blocker','Critical','Medium','Low','QoL')"
            ) as cur:
                row = await cur.fetchone()
            wrong_class_count = int(row[0]) if row else 0
    assert wrong_class_count == 0


@pytest.mark.asyncio
async def test_second_call_is_idempotent() -> None:
    """Re-calling ensure_severity_tags does not duplicate severity tags."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        factory = get_connection_factory(db_path)
        async with factory() as conn:
            await load_schema(conn)
            await ensure_severity_tags(conn)
            # Second call — must be idempotent.
            await ensure_severity_tags(conn)
            count = await _count_severity_tags(conn)
    assert count == EXPECTED_SEVERITY_COUNT


@pytest.mark.asyncio
async def test_seeder_skips_existing_severity_names() -> None:
    """Seeder does not insert a severity tag if that name already exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        factory = get_connection_factory(db_path)
        async with factory() as conn:
            await load_schema(conn)
            await ensure_severity_tags(conn)
            count_before = await _count_severity_tags(conn)
            await ensure_severity_tags(conn)
            count_after = await _count_severity_tags(conn)
    assert count_before == EXPECTED_SEVERITY_COUNT
    assert count_after == EXPECTED_SEVERITY_COUNT
