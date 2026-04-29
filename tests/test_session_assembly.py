"""Tests for :mod:`bearings.agent.session_assembly` overlay chain.

Covers each layer of the precedence (global → template → tags →
explicit) plus the SessionAssemblyError raised when working_dir has
no source.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from bearings.agent.session_assembly import (
    SessionAssemblyError,
    build_session_config,
)
from bearings.config.constants import (
    DEFAULT_TEMPLATE_ADVISOR_MODEL,
    DEFAULT_TEMPLATE_EFFORT_LEVEL,
    DEFAULT_TEMPLATE_MODEL,
)
from bearings.db import tags as tags_db
from bearings.db import templates as templates_db
from bearings.db.connection import load_schema


@pytest.fixture
async def conn(tmp_path: Path):
    db_path = tmp_path / "asm.db"
    async with aiosqlite.connect(db_path) as connection:
        await load_schema(connection)
        yield connection


async def test_pure_global_default(conn: aiosqlite.Connection) -> None:
    """No tags, no template, no explicit input — global default."""
    config = await build_session_config(
        conn,
        session_id="ses_test",
        working_dir="/explicit/wd",  # working_dir has no global default
    )
    decision = config.decision
    # working_dir is the only explicit signal; mark source=manual.
    assert decision.source == "manual"
    assert decision.executor_model == DEFAULT_TEMPLATE_MODEL
    assert decision.advisor_model == DEFAULT_TEMPLATE_ADVISOR_MODEL
    assert decision.effort_level == DEFAULT_TEMPLATE_EFFORT_LEVEL


async def test_no_signals_at_all_marks_source_default(conn: aiosqlite.Connection) -> None:
    """When nothing is supplied AND a tag with working_dir bridges the gap.

    The pure-default test above can't avoid the explicit working_dir
    because there's no global fallback for that field; supply it via
    a tag so the source-resolution path sees zero explicit signal.
    """
    tag = await tags_db.create(conn, name="def-tag", working_dir="/from/tag", default_model=None)
    config = await build_session_config(conn, session_id="ses_x", tag_ids=[tag.id])
    # Tag had no default_model so source stays "default".
    assert config.decision.source == "default"
    assert config.working_dir == "/from/tag"


async def test_explicit_overrides_tag_overrides_template(
    conn: aiosqlite.Connection,
) -> None:
    """Layer ordering: explicit > tag > template > global."""
    template = await templates_db.create(
        conn,
        name="t",
        model="haiku",
        advisor_model="opus",
        effort_level="low",
        permission_profile="standard",
        working_dir_default="/template/wd",
    )
    tag = await tags_db.create(conn, name="tag-a", default_model="opus", working_dir="/tag/wd")
    # No explicit model — tag's "opus" should win over template's "haiku".
    no_explicit = await build_session_config(
        conn,
        session_id="ses_no_explicit",
        template_id=template.id,
        tag_ids=[tag.id],
    )
    assert no_explicit.decision.executor_model == "opus"
    assert no_explicit.working_dir == "/tag/wd"
    # Explicit model — should win over both.
    with_explicit = await build_session_config(
        conn,
        session_id="ses_explicit",
        template_id=template.id,
        tag_ids=[tag.id],
        model="sonnet",
        working_dir="/user/wd",
    )
    assert with_explicit.decision.executor_model == "sonnet"
    assert with_explicit.working_dir == "/user/wd"


async def test_template_overlay_when_no_tag_supplies_model(
    conn: aiosqlite.Connection,
) -> None:
    template = await templates_db.create(
        conn,
        name="t2",
        model="haiku",
        effort_level="medium",
        permission_profile="standard",
        working_dir_default="/template/wd",
    )
    config = await build_session_config(conn, session_id="ses_template", template_id=template.id)
    assert config.decision.executor_model == "haiku"
    assert config.decision.effort_level == "medium"
    assert config.working_dir == "/template/wd"


async def test_advisor_disabled_via_empty_string(conn: aiosqlite.Connection) -> None:
    config = await build_session_config(
        conn,
        session_id="ses_no_advisor",
        working_dir="/wd",
        advisor_model="",  # empty string positively disables advisor
    )
    assert config.decision.advisor_model is None


async def test_missing_working_dir_raises(conn: aiosqlite.Connection) -> None:
    """No overlay supplies working_dir → SessionAssemblyError."""
    with pytest.raises(SessionAssemblyError, match="working_dir"):
        await build_session_config(conn, session_id="ses_x")


async def test_missing_template_raises(conn: aiosqlite.Connection) -> None:
    from bearings.agent.templates import TemplateNotFoundError

    with pytest.raises(TemplateNotFoundError):
        await build_session_config(conn, session_id="ses_y", working_dir="/wd", template_id=9999)


async def test_unknown_tag_id_silently_dropped(conn: aiosqlite.Connection) -> None:
    """Tag id pointing at a deleted row is dropped (not raised)."""
    config = await build_session_config(conn, session_id="ses_z", working_dir="/wd", tag_ids=[9999])
    # Falls back to global default.
    assert config.decision.executor_model == DEFAULT_TEMPLATE_MODEL


async def test_routing_source_default_when_no_signals(
    conn: aiosqlite.Connection,
) -> None:
    """A tag that supplies only working_dir (no model) is *not* a model
    contribution — source stays 'default'."""
    tag = await tags_db.create(conn, name="wd-only", working_dir="/from/tag")
    config = await build_session_config(conn, session_id="ses_d", tag_ids=[tag.id])
    assert config.decision.source == "default"


async def test_tag_with_default_model_marks_source_manual(
    conn: aiosqlite.Connection,
) -> None:
    tag = await tags_db.create(conn, name="modeled", default_model="haiku", working_dir="/wd")
    config = await build_session_config(conn, session_id="ses_m", tag_ids=[tag.id])
    assert config.decision.source == "manual"
    assert config.decision.executor_model == "haiku"
