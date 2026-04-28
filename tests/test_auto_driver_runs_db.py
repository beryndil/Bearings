"""DB-layer tests for ``bearings.db.auto_driver_runs``.

Covers run-row CRUD, the state-transition table, counter updates,
and finalize semantics from ``docs/behavior/checklists.md``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest

from bearings.config.constants import (
    AUTO_DRIVER_FAILURE_POLICY_HALT,
    AUTO_DRIVER_FAILURE_POLICY_SKIP,
    AUTO_DRIVER_STATE_ERRORED,
    AUTO_DRIVER_STATE_FINISHED,
    AUTO_DRIVER_STATE_IDLE,
    AUTO_DRIVER_STATE_PAUSED,
    AUTO_DRIVER_STATE_RUNNING,
    DRIVER_OUTCOME_COMPLETED,
)
from bearings.db import get_connection_factory, load_schema
from bearings.db.auto_driver_runs import (
    AutoDriverRun,
    can_transition,
    create,
    finalize,
    get,
    get_active,
    list_for_checklist,
    update_counters,
    update_state,
)


@pytest.fixture
async def connection(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    factory = get_connection_factory(tmp_path / "runs.db")
    async with factory() as conn:
        await load_schema(conn)
        await conn.execute(
            "INSERT INTO sessions (id, kind, title, working_dir, model, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("chk_1", "checklist", "T", "/tmp", "sonnet", "2026-01-01", "2026-01-01"),
        )
        await conn.commit()
        yield conn


def test_can_transition_table() -> None:
    # Legal edges
    assert can_transition(AUTO_DRIVER_STATE_IDLE, AUTO_DRIVER_STATE_RUNNING)
    assert can_transition(AUTO_DRIVER_STATE_RUNNING, AUTO_DRIVER_STATE_PAUSED)
    assert can_transition(AUTO_DRIVER_STATE_RUNNING, AUTO_DRIVER_STATE_FINISHED)
    assert can_transition(AUTO_DRIVER_STATE_RUNNING, AUTO_DRIVER_STATE_ERRORED)
    assert can_transition(AUTO_DRIVER_STATE_PAUSED, AUTO_DRIVER_STATE_RUNNING)
    assert can_transition(AUTO_DRIVER_STATE_PAUSED, AUTO_DRIVER_STATE_FINISHED)
    # Illegal edges
    assert not can_transition(AUTO_DRIVER_STATE_FINISHED, AUTO_DRIVER_STATE_RUNNING)
    assert not can_transition(AUTO_DRIVER_STATE_ERRORED, AUTO_DRIVER_STATE_RUNNING)
    assert not can_transition(AUTO_DRIVER_STATE_IDLE, AUTO_DRIVER_STATE_PAUSED)
    assert not can_transition("bogus", AUTO_DRIVER_STATE_RUNNING)
    assert not can_transition(AUTO_DRIVER_STATE_RUNNING, "bogus")


async def test_create_default_state_running(
    connection: aiosqlite.Connection,
) -> None:
    run = await create(connection, checklist_id="chk_1")
    assert isinstance(run, AutoDriverRun)
    assert run.state == AUTO_DRIVER_STATE_RUNNING
    assert run.failure_policy == AUTO_DRIVER_FAILURE_POLICY_HALT
    assert run.visit_existing is False
    assert run.items_completed == 0
    assert run.outcome is None


async def test_create_with_idle_initial_state(
    connection: aiosqlite.Connection,
) -> None:
    run = await create(
        connection,
        checklist_id="chk_1",
        initial_state=AUTO_DRIVER_STATE_IDLE,
    )
    assert run.state == AUTO_DRIVER_STATE_IDLE


async def test_create_rejects_unknown_state(
    connection: aiosqlite.Connection,
) -> None:
    with pytest.raises(ValueError, match="initial_state"):
        await create(connection, checklist_id="chk_1", initial_state="bogus")


async def test_create_with_visit_existing_and_skip_policy(
    connection: aiosqlite.Connection,
) -> None:
    run = await create(
        connection,
        checklist_id="chk_1",
        failure_policy=AUTO_DRIVER_FAILURE_POLICY_SKIP,
        visit_existing=True,
    )
    assert run.failure_policy == AUTO_DRIVER_FAILURE_POLICY_SKIP
    assert run.visit_existing is True


async def test_get_returns_none_when_absent(
    connection: aiosqlite.Connection,
) -> None:
    assert await get(connection, 99_999) is None


async def test_get_active_returns_running(connection: aiosqlite.Connection) -> None:
    run = await create(connection, checklist_id="chk_1")
    active = await get_active(connection, "chk_1")
    assert active is not None
    assert active.id == run.id


async def test_get_active_returns_paused(connection: aiosqlite.Connection) -> None:
    run = await create(connection, checklist_id="chk_1")
    await update_state(connection, run.id, state=AUTO_DRIVER_STATE_PAUSED)
    active = await get_active(connection, "chk_1")
    assert active is not None
    assert active.state == AUTO_DRIVER_STATE_PAUSED


async def test_get_active_excludes_finished(
    connection: aiosqlite.Connection,
) -> None:
    run = await create(connection, checklist_id="chk_1")
    await finalize(
        connection,
        run.id,
        state=AUTO_DRIVER_STATE_FINISHED,
        outcome=DRIVER_OUTCOME_COMPLETED,
    )
    assert await get_active(connection, "chk_1") is None


async def test_list_for_checklist_newest_first(
    connection: aiosqlite.Connection,
) -> None:
    run1 = await create(connection, checklist_id="chk_1")
    await finalize(
        connection,
        run1.id,
        state=AUTO_DRIVER_STATE_FINISHED,
        outcome=DRIVER_OUTCOME_COMPLETED,
    )
    run2 = await create(connection, checklist_id="chk_1")
    runs = await list_for_checklist(connection, "chk_1")
    assert runs[0].id == run2.id
    assert runs[1].id == run1.id


async def test_update_state_legal_transition(
    connection: aiosqlite.Connection,
) -> None:
    run = await create(connection, checklist_id="chk_1")
    paused = await update_state(connection, run.id, state=AUTO_DRIVER_STATE_PAUSED)
    assert paused is not None
    assert paused.state == AUTO_DRIVER_STATE_PAUSED


async def test_update_state_rejects_illegal_transition(
    connection: aiosqlite.Connection,
) -> None:
    run = await create(connection, checklist_id="chk_1")
    await finalize(
        connection,
        run.id,
        state=AUTO_DRIVER_STATE_FINISHED,
        outcome=DRIVER_OUTCOME_COMPLETED,
    )
    with pytest.raises(ValueError, match="illegal"):
        await update_state(connection, run.id, state=AUTO_DRIVER_STATE_RUNNING)


async def test_update_state_returns_none_when_absent(
    connection: aiosqlite.Connection,
) -> None:
    assert await update_state(connection, 99_999, state=AUTO_DRIVER_STATE_RUNNING) is None


async def test_update_counters_replaces_subset(
    connection: aiosqlite.Connection,
) -> None:
    run = await create(connection, checklist_id="chk_1")
    updated = await update_counters(
        connection,
        run.id,
        items_completed=2,
        legs_spawned=3,
        current_item_id=None,
    )
    assert updated is not None
    assert updated.items_completed == 2
    assert updated.legs_spawned == 3
    # Untouched counters preserved
    assert updated.items_failed == 0


async def test_update_counters_clear_current_item(
    connection: aiosqlite.Connection,
) -> None:
    # Need a real checklist_item id for the FK on current_item_id
    from bearings.db.checklists import create as create_item

    item = await create_item(connection, checklist_id="chk_1", label="L")
    run = await create(connection, checklist_id="chk_1")
    # First, set a current_item_id
    await update_counters(connection, run.id, current_item_id=item.id)
    fetched = await get(connection, run.id)
    assert fetched is not None
    assert fetched.current_item_id == item.id
    # Now clear it
    cleared = await update_counters(connection, run.id, clear_current_item=True)
    assert cleared is not None
    assert cleared.current_item_id is None


async def test_update_counters_rejects_negative(
    connection: aiosqlite.Connection,
) -> None:
    run = await create(connection, checklist_id="chk_1")
    with pytest.raises(ValueError, match="≥ 0"):
        await update_counters(connection, run.id, items_completed=-1)


async def test_finalize_stamps_outcome_and_finished_at(
    connection: aiosqlite.Connection,
) -> None:
    run = await create(connection, checklist_id="chk_1")
    final = await finalize(
        connection,
        run.id,
        state=AUTO_DRIVER_STATE_FINISHED,
        outcome=DRIVER_OUTCOME_COMPLETED,
        outcome_reason=None,
    )
    assert final is not None
    assert final.state == AUTO_DRIVER_STATE_FINISHED
    assert final.outcome == DRIVER_OUTCOME_COMPLETED
    assert final.finished_at is not None


async def test_finalize_rejects_non_terminal_state(
    connection: aiosqlite.Connection,
) -> None:
    run = await create(connection, checklist_id="chk_1")
    with pytest.raises(ValueError, match="terminal"):
        await finalize(
            connection,
            run.id,
            state=AUTO_DRIVER_STATE_RUNNING,
            outcome="X",
        )


async def test_finalize_rejects_empty_outcome(
    connection: aiosqlite.Connection,
) -> None:
    run = await create(connection, checklist_id="chk_1")
    with pytest.raises(ValueError, match="outcome"):
        await finalize(
            connection,
            run.id,
            state=AUTO_DRIVER_STATE_FINISHED,
            outcome="",
        )


async def test_dataclass_validates_negative_counter() -> None:
    with pytest.raises(ValueError, match="≥ 0"):
        AutoDriverRun(
            id=1,
            checklist_id="chk",
            state=AUTO_DRIVER_STATE_RUNNING,
            failure_policy=AUTO_DRIVER_FAILURE_POLICY_HALT,
            visit_existing=False,
            items_completed=-1,
            items_failed=0,
            items_blocked=0,
            items_skipped=0,
            items_attempted=0,
            legs_spawned=0,
            current_item_id=None,
            outcome=None,
            outcome_reason=None,
            started_at="2026-01-01",
            updated_at="2026-01-01",
            finished_at=None,
        )
