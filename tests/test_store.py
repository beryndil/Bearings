from __future__ import annotations

from pathlib import Path

import pytest

from twrminal.db.store import init_db


@pytest.mark.asyncio
async def test_init_db_creates_tables(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cursor:
            tables = [row[0] async for row in cursor]
        assert "sessions" in tables
        assert "messages" in tables
        assert "tool_calls" in tables
        assert "schema_migrations" in tables
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_init_db_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    conn1 = await init_db(db_path)
    await conn1.close()
    conn2 = await init_db(db_path)
    try:
        async with conn2.execute("SELECT count(*) FROM schema_migrations") as cursor:
            row = await cursor.fetchone()
        assert row is not None and row[0] == 1
    finally:
        await conn2.close()
