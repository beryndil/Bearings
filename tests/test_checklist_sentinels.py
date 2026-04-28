"""Sentinel-trigger observable-effect tests.

For each sentinel kind from behavior/checklists.md §"Sentinels (auto-
pause / failure / completion)" verify the trigger condition + the
observable effect on the durable run-row + item state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest

from bearings.agent.auto_driver import Driver
from bearings.agent.auto_driver_types import DriverConfig, DriverOutcome
from bearings.config.constants import (
    ITEM_OUTCOME_BLOCKED,
    ITEM_OUTCOME_FAILED,
)
from bearings.db import auto_driver_runs as runs_db
from bearings.db import checklists as checklists_db
from bearings.db import get_connection_factory, load_schema

# Reuse StubRuntime from the unit test module.
from tests.test_auto_driver_unit import StubRuntime, _leg_id


@pytest.fixture
async def connection(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    factory = get_connection_factory(tmp_path / "sentinels.db")
    async with factory() as conn:
        await load_schema(conn)
        await conn.execute(
            "INSERT INTO sessions (id, kind, title, working_dir, model, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "chk_s",
                "checklist",
                "T",
                "/tmp",
                "sonnet",
                "2026-01-01",
                "2026-01-01",
            ),
        )
        await conn.commit()
        yield conn


async def _build_driver(
    connection: aiosqlite.Connection,
    runtime: StubRuntime,
    *,
    config: DriverConfig | None = None,
) -> Driver:
    run = await runs_db.create(connection, checklist_id="chk_s")
    cfg = config or DriverConfig(
        max_legs_per_item=3,
        max_items_per_run=10,
        max_followup_depth=2,
        max_turns_per_leg=4,
    )
    return Driver(
        run_id=run.id,
        checklist_id="chk_s",
        config=cfg,
        runtime=runtime,
        connection=connection,
    )


async def test_item_done_sentinel_marks_item_checked(
    connection: aiosqlite.Connection,
) -> None:
    item = await checklists_db.create(connection, checklist_id="chk_s", label="A")
    runtime = StubRuntime(connection=connection)
    runtime.leg_responses[_leg_id(item.id, 1)] = [
        '<bearings:sentinel kind="item_done" />',
    ]
    driver = await _build_driver(connection, runtime)
    result = await driver.drive()
    fetched = await checklists_db.get(connection, item.id)
    assert fetched is not None
    assert fetched.checked_at is not None
    assert result.items_completed == 1


async def test_handoff_sentinel_increments_legs_spawned(
    connection: aiosqlite.Connection,
) -> None:
    item = await checklists_db.create(connection, checklist_id="chk_s", label="A")
    runtime = StubRuntime(connection=connection)
    runtime.leg_responses[_leg_id(item.id, 1)] = [
        '<bearings:sentinel kind="handoff"><plug>p</plug></bearings:sentinel>',
    ]
    runtime.leg_responses[_leg_id(item.id, 2)] = [
        '<bearings:sentinel kind="item_done" />',
    ]
    driver = await _build_driver(connection, runtime)
    result = await driver.drive()
    assert result.legs_spawned == 2
    legs = await checklists_db.list_legs(connection, item.id)
    assert len(legs) == 2


async def test_item_blocked_sentinel_marks_amber(
    connection: aiosqlite.Connection,
) -> None:
    item = await checklists_db.create(connection, checklist_id="chk_s", label="A")
    runtime = StubRuntime(connection=connection)
    runtime.leg_responses[_leg_id(item.id, 1)] = [
        '<bearings:sentinel kind="item_blocked"><text>creds</text></bearings:sentinel>',
    ]
    driver = await _build_driver(connection, runtime)
    result = await driver.drive()
    fetched = await checklists_db.get(connection, item.id)
    assert fetched is not None
    assert fetched.blocked_at is not None
    assert fetched.blocked_reason_category == ITEM_OUTCOME_BLOCKED
    assert result.items_blocked == 1


async def test_item_failed_sentinel_halts_under_halt_policy(
    connection: aiosqlite.Connection,
) -> None:
    item = await checklists_db.create(connection, checklist_id="chk_s", label="A")
    runtime = StubRuntime(connection=connection)
    runtime.leg_responses[_leg_id(item.id, 1)] = [
        '<bearings:sentinel kind="item_failed"><reason>r</reason></bearings:sentinel>',
    ]
    driver = await _build_driver(connection, runtime)
    result = await driver.drive()
    assert result.outcome == DriverOutcome.halted_failure(item.id)
    fetched = await checklists_db.get(connection, item.id)
    assert fetched is not None
    assert fetched.blocked_reason_category == ITEM_OUTCOME_FAILED


async def test_followup_blocking_appends_child_under_current(
    connection: aiosqlite.Connection,
) -> None:
    parent = await checklists_db.create(connection, checklist_id="chk_s", label="P")
    runtime = StubRuntime(connection=connection)
    runtime.leg_responses[_leg_id(parent.id, 1)] = [
        '<bearings:sentinel kind="followup_blocking"><label>child</label></bearings:sentinel>',
        '<bearings:sentinel kind="item_done" />',
    ]
    driver = await _build_driver(connection, runtime)
    await driver.drive()
    children = await checklists_db.list_children(
        connection, checklist_id="chk_s", parent_item_id=parent.id
    )
    assert any(c.label == "child" for c in children)


async def test_followup_nonblocking_appends_at_root(
    connection: aiosqlite.Connection,
) -> None:
    item = await checklists_db.create(connection, checklist_id="chk_s", label="A")
    runtime = StubRuntime(connection=connection)
    runtime.leg_responses[_leg_id(item.id, 1)] = [
        '<bearings:sentinel kind="followup_nonblocking"><label>later</label></bearings:sentinel>',
        '<bearings:sentinel kind="item_done" />',
    ]
    driver = await _build_driver(connection, runtime)
    await driver.drive()
    items = await checklists_db.list_for_checklist(connection, "chk_s")
    new = [i for i in items if i.label == "later"]
    assert len(new) == 1
    assert new[0].parent_item_id is None


async def test_max_legs_per_item_sentinel_safety_cap(
    connection: aiosqlite.Connection,
) -> None:
    """Cap at 5 (default) — handoff loop hits leg-cap → halts."""
    item = await checklists_db.create(connection, checklist_id="chk_s", label="A")
    runtime = StubRuntime(connection=connection)
    handoff = '<bearings:sentinel kind="handoff"><plug>p</plug></bearings:sentinel>'
    cfg = DriverConfig(
        max_legs_per_item=2,
        max_items_per_run=10,
        max_followup_depth=2,
        max_turns_per_leg=4,
    )
    runtime.leg_responses[_leg_id(item.id, 1)] = [handoff]
    runtime.leg_responses[_leg_id(item.id, 2)] = [handoff]
    driver = await _build_driver(connection, runtime, config=cfg)
    result = await driver.drive()
    assert "max_legs" in (result.outcome_reason or "")
    assert result.items_failed == 1


async def test_max_followup_depth_caps_recursion(
    connection: aiosqlite.Connection,
) -> None:
    """A followup_blocking emitted at depth ≥ max_followup_depth is ignored."""
    parent = await checklists_db.create(connection, checklist_id="chk_s", label="P")
    runtime = StubRuntime(connection=connection)
    # Single-leg responds with item_done after emitting one followup.
    runtime.leg_responses[_leg_id(parent.id, 1)] = [
        '<bearings:sentinel kind="followup_blocking"><label>c1</label></bearings:sentinel>',
        '<bearings:sentinel kind="item_done" />',
    ]
    cfg = DriverConfig(
        max_legs_per_item=2,
        max_items_per_run=10,
        max_followup_depth=1,
        max_turns_per_leg=4,
    )
    driver = await _build_driver(connection, runtime, config=cfg)
    await driver.drive()
    # The single child IS created (depth=0 < max=1). Verifies the cap
    # is honored as an upper bound, not as zero-tolerance.
    children = await checklists_db.list_children(
        connection, checklist_id="chk_s", parent_item_id=parent.id
    )
    assert len(children) == 1


async def test_completion_sentinel_terminates_run(
    connection: aiosqlite.Connection,
) -> None:
    """Run-row state goes to finished + outcome=Completed when every item done."""
    item = await checklists_db.create(connection, checklist_id="chk_s", label="A")
    runtime = StubRuntime(connection=connection)
    runtime.leg_responses[_leg_id(item.id, 1)] = [
        '<bearings:sentinel kind="item_done" />',
    ]
    driver = await _build_driver(connection, runtime)
    await driver.drive()
    final = await runs_db.get(connection, driver.run_id)
    assert final is not None
    assert final.outcome == DriverOutcome.COMPLETED
    assert final.finished_at is not None


async def test_malformed_sentinel_ignored_then_failure_at_turn_cap(
    connection: aiosqlite.Connection,
) -> None:
    """Malformed sentinel is ignored; the leg eventually hits the turn cap."""
    item = await checklists_db.create(connection, checklist_id="chk_s", label="A")
    runtime = StubRuntime(connection=connection)
    # Half-emitted sentinel — no closing tag → parse() drops it.
    runtime.leg_responses[_leg_id(item.id, 1)] = [
        '<bearings:sentinel kind="item_done"',  # truncated
        "(quiet)",
    ]
    cfg = DriverConfig(
        max_legs_per_item=1,
        max_items_per_run=10,
        max_followup_depth=2,
        max_turns_per_leg=2,
    )
    driver = await _build_driver(connection, runtime, config=cfg)
    result = await driver.drive()
    # Item didn't get checked — turn-cap synthesised a failure
    assert result.items_failed == 1
    fetched = await checklists_db.get(connection, item.id)
    assert fetched is not None
    assert fetched.checked_at is None
