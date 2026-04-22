"""Slice 4 of nimble-checking-heron: per-item paired chat sessions.

Covers the symmetric FK pairing introduced by migration 0017, the
store-level helpers (`set_item_chat_session`, `get_item_by_chat_session`,
`create_session(checklist_item_id=...)`), the `checklist_context`
prompt layer, and the HTTP surface (POST/GET paired chat).

Shape mirrors `test_checklists.py` for the store-level cases and
`test_routes_checklists.py` for the HTTP cases — no WS plumbing is
involved; paired chats open as regular chat sessions on the WS side.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bearings.agent.prompt import assemble_prompt
from bearings.db.store import (
    attach_tag,
    create_checklist,
    create_item,
    create_session,
    create_tag,
    delete_item,
    delete_session,
    get_item,
    get_item_by_chat_session,
    get_session,
    init_db,
    set_item_chat_session,
    toggle_item,
)

# ---------------------------------------------------------------------------
# Migration shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_adds_symmetric_pairing_columns(tmp_path: Path) -> None:
    """After migration 0017, both `checklist_items.chat_session_id` and
    `sessions.checklist_item_id` must exist with ON DELETE SET NULL."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        async with conn.execute("PRAGMA table_info(checklist_items)") as cursor:
            item_cols = {row[1] async for row in cursor}
        async with conn.execute("PRAGMA table_info(sessions)") as cursor:
            session_cols = {row[1] async for row in cursor}
        assert "chat_session_id" in item_cols
        assert "checklist_item_id" in session_cols
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_migration_creates_pairing_indexes(tmp_path: Path) -> None:
    """Point-lookup indexes on both pairing sides land with the migration."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name IN ('idx_checklist_items_chat_session', 'idx_sessions_checklist_item')"
        ) as cursor:
            idx = {row[0] async for row in cursor}
        assert idx == {"idx_checklist_items_chat_session", "idx_sessions_checklist_item"}
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Store surface: pairing helpers
# ---------------------------------------------------------------------------


async def _make_checklist_with_item(conn: Any, label: str = "task") -> tuple[str, int]:
    """Shortcut: checklist session + body + one item; returns (session_id, item_id)."""
    cl = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist")
    await create_checklist(conn, cl["id"])
    item = await create_item(conn, cl["id"], label=label)
    assert item is not None
    return cl["id"], item["id"]


@pytest.mark.asyncio
async def test_create_session_with_checklist_item_id_round_trips(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        _cl_id, item_id = await _make_checklist_with_item(conn)
        chat = await create_session(
            conn,
            working_dir="/tmp",
            model="claude-sonnet-4-6",
            kind="chat",
            checklist_item_id=item_id,
        )
        assert chat["checklist_item_id"] == item_id
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_create_session_rejects_checklist_item_id_on_non_chat(tmp_path: Path) -> None:
    """Pairing is chat-only. A `kind='checklist'` session paired to an
    item makes no sense and must raise before hitting SQLite."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        _cl_id, item_id = await _make_checklist_with_item(conn)
        with pytest.raises(ValueError):
            await create_session(
                conn,
                working_dir="/tmp",
                model="claude-sonnet-4-6",
                kind="checklist",
                checklist_item_id=item_id,
            )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_set_item_chat_session_round_trips(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        _cl_id, item_id = await _make_checklist_with_item(conn)
        chat = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6")
        updated = await set_item_chat_session(conn, item_id, chat["id"])
        assert updated is not None
        assert updated["chat_session_id"] == chat["id"]
        cleared = await set_item_chat_session(conn, item_id, None)
        assert cleared is not None
        assert cleared["chat_session_id"] is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_set_item_chat_session_on_missing_item_returns_none(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        assert await set_item_chat_session(conn, 9999, None) is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_get_item_by_chat_session_reverse_lookup(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        _cl_id, item_id = await _make_checklist_with_item(conn, label="do X")
        chat = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6")
        await set_item_chat_session(conn, item_id, chat["id"])
        found = await get_item_by_chat_session(conn, chat["id"])
        assert found is not None
        assert found["id"] == item_id
        assert found["label"] == "do X"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_get_item_by_chat_session_missing_returns_none(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        assert await get_item_by_chat_session(conn, "no-such-chat") is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_set_null_cascade_on_chat_delete(tmp_path: Path) -> None:
    """Deleting the chat session must null out `chat_session_id` on the
    paired item (ON DELETE SET NULL), not cascade-delete the item."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        _cl_id, item_id = await _make_checklist_with_item(conn)
        chat = await create_session(
            conn,
            working_dir="/tmp",
            model="claude-sonnet-4-6",
            kind="chat",
            checklist_item_id=item_id,
        )
        await set_item_chat_session(conn, item_id, chat["id"])
        await delete_session(conn, chat["id"])
        after = await get_item(conn, item_id)
        assert after is not None  # item itself not deleted
        assert after["chat_session_id"] is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_set_null_cascade_on_item_delete(tmp_path: Path) -> None:
    """Deleting the checklist item must null out `checklist_item_id` on
    the paired chat — the chat degrades to a plain session rather than
    losing its history."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        _cl_id, item_id = await _make_checklist_with_item(conn)
        chat = await create_session(
            conn,
            working_dir="/tmp",
            model="claude-sonnet-4-6",
            kind="chat",
            checklist_item_id=item_id,
        )
        await set_item_chat_session(conn, item_id, chat["id"])
        await delete_item(conn, item_id)
        after = await get_session(conn, chat["id"])
        assert after is not None  # chat itself not deleted
        assert after["checklist_item_id"] is None
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Prompt assembler: checklist_context layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_prompt_injects_checklist_context_when_paired(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        cl = await create_session(
            conn,
            working_dir="/tmp",
            model="claude-sonnet-4-6",
            kind="checklist",
            title="release checklist",
        )
        await create_checklist(conn, cl["id"], notes="ship v0.5.0 safely")
        item = await create_item(
            conn, cl["id"], label="run quality gates", notes="ruff+mypy+pytest"
        )
        assert item is not None
        chat = await create_session(
            conn,
            working_dir="/tmp",
            model="claude-sonnet-4-6",
            kind="chat",
            checklist_item_id=item["id"],
        )
        result = await assemble_prompt(conn, chat["id"])
    finally:
        await conn.close()
    kinds = [layer.kind for layer in result.layers]
    assert "checklist_context" in kinds
    ctx_layer = next(layer for layer in result.layers if layer.kind == "checklist_context")
    assert "run quality gates" in ctx_layer.content
    assert "ship v0.5.0 safely" in ctx_layer.content
    assert "ruff+mypy+pytest" in ctx_layer.content
    assert "release checklist" in ctx_layer.content
    assert "UNCHECKED" in ctx_layer.content


@pytest.mark.asyncio
async def test_assemble_prompt_omits_layer_for_unpaired_chat(tmp_path: Path) -> None:
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        chat = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6")
        result = await assemble_prompt(conn, chat["id"])
    finally:
        await conn.close()
    assert "checklist_context" not in [layer.kind for layer in result.layers]


@pytest.mark.asyncio
async def test_assemble_prompt_renders_sibling_summary_with_glyphs(tmp_path: Path) -> None:
    """Sibling list uses `[x]`/`[ ]` glyphs derived from `checked_at`."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        cl = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        await create_checklist(conn, cl["id"])
        focus = await create_item(conn, cl["id"], label="focus item")
        done = await create_item(conn, cl["id"], label="done item")
        pending = await create_item(conn, cl["id"], label="pending item")
        assert focus and done and pending
        await toggle_item(conn, done["id"], checked=True)
        chat = await create_session(
            conn,
            working_dir="/tmp",
            model="claude-sonnet-4-6",
            kind="chat",
            checklist_item_id=focus["id"],
        )
        result = await assemble_prompt(conn, chat["id"])
    finally:
        await conn.close()
    ctx = next(layer for layer in result.layers if layer.kind == "checklist_context")
    # Focus item appears as the "Current item", not among siblings.
    assert "Current item" in ctx.content
    assert "focus item" in ctx.content
    assert "[x] done item" in ctx.content
    assert "[ ] pending item" in ctx.content
    # The focus item itself must not appear in the sibling block.
    focus_sibling_line = "[ ] focus item"
    assert focus_sibling_line not in ctx.content


@pytest.mark.asyncio
async def test_assemble_prompt_handles_checked_focus_item(tmp_path: Path) -> None:
    """A paired chat on a checked item shows `CHECKED` in the layer."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        cl = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        await create_checklist(conn, cl["id"])
        item = await create_item(conn, cl["id"], label="already done")
        assert item is not None
        await toggle_item(conn, item["id"], checked=True)
        chat = await create_session(
            conn,
            working_dir="/tmp",
            model="claude-sonnet-4-6",
            kind="chat",
            checklist_item_id=item["id"],
        )
        result = await assemble_prompt(conn, chat["id"])
    finally:
        await conn.close()
    ctx = next(layer for layer in result.layers if layer.kind == "checklist_context")
    assert "CHECKED" in ctx.content
    assert "UNCHECKED" not in ctx.content


@pytest.mark.asyncio
async def test_assemble_prompt_skips_layer_on_stale_pairing(tmp_path: Path) -> None:
    """If the item pointed to by `checklist_item_id` is gone (FK should
    null out but an in-flight row may still carry a stale id), the
    assembler skips the layer instead of crashing."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        chat = await create_session(conn, working_dir="/tmp", model="claude-sonnet-4-6")
        # Wedge a stale pointer — drop FKs briefly to simulate the
        # narrow race where the item-delete cascade hasn't propagated
        # to this connection yet.
        await conn.execute("PRAGMA foreign_keys = OFF")
        await conn.execute(
            "UPDATE sessions SET checklist_item_id = 99999 WHERE id = ?",
            (chat["id"],),
        )
        await conn.commit()
        await conn.execute("PRAGMA foreign_keys = ON")
        result = await assemble_prompt(conn, chat["id"])
    finally:
        await conn.close()
    assert "checklist_context" not in [layer.kind for layer in result.layers]


@pytest.mark.asyncio
async def test_assemble_prompt_layer_order_puts_checklist_before_session(tmp_path: Path) -> None:
    """Layer order: base → description → tag_memory → checklist_context → session."""
    conn = await init_db(tmp_path / "db.sqlite")
    try:
        cl = await create_session(
            conn, working_dir="/tmp", model="claude-sonnet-4-6", kind="checklist"
        )
        await create_checklist(conn, cl["id"])
        item = await create_item(conn, cl["id"], label="one")
        assert item is not None
        tag = await create_tag(conn, name="eng")
        await conn.execute(
            "INSERT INTO tag_memories (tag_id, content, updated_at) VALUES (?, ?, datetime('now'))",
            (tag["id"], "tag content"),
        )
        await conn.commit()
        chat = await create_session(
            conn,
            working_dir="/tmp",
            model="claude-sonnet-4-6",
            kind="chat",
            description="why this chat exists",
            checklist_item_id=item["id"],
        )
        await attach_tag(conn, chat["id"], tag["id"])
        await conn.execute(
            "UPDATE sessions SET session_instructions = ? WHERE id = ?",
            ("final override", chat["id"]),
        )
        await conn.commit()
        result = await assemble_prompt(conn, chat["id"])
    finally:
        await conn.close()
    assert [layer.kind for layer in result.layers] == [
        "base",
        "session_description",
        "tag_memory",
        "checklist_context",
        "session",
    ]


# ---------------------------------------------------------------------------
# HTTP surface: POST / GET paired chat
# ---------------------------------------------------------------------------


def _default_tag(client: TestClient) -> int:
    existing = client.get("/api/tags").json()
    if existing:
        return int(existing[0]["id"])
    created = client.post("/api/tags", json={"name": "default"})
    return int(created.json()["id"])


def _create_checklist_with_item(
    client: TestClient, *, label: str = "task", tag_ids: list[int] | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    body = {
        "working_dir": "/tmp",
        "model": "claude-sonnet-4-6",
        "title": "plan",
        "tag_ids": tag_ids or [_default_tag(client)],
        "kind": "checklist",
    }
    cl_resp = client.post("/api/sessions", json=body)
    assert cl_resp.status_code == 200, cl_resp.text
    cl = cl_resp.json()
    item_resp = client.post(
        f"/api/sessions/{cl['id']}/checklist/items",
        json={"label": label},
    )
    assert item_resp.status_code == 201, item_resp.text
    return cl, item_resp.json()


def test_spawn_paired_chat_creates_chat_session(client: TestClient) -> None:
    cl, item = _create_checklist_with_item(client, label="prep release")
    resp = client.post(
        f"/api/sessions/{cl['id']}/checklist/items/{item['id']}/chat",
        json={},
    )
    assert resp.status_code == 201, resp.text
    chat = resp.json()
    assert chat["kind"] == "chat"
    assert chat["checklist_item_id"] == item["id"]
    # Title inherits the item label by default.
    assert chat["title"] == "prep release"
    # Item's forward pointer was wired up.
    listing = client.get(f"/api/sessions/{cl['id']}/checklist").json()
    paired_item = next(i for i in listing["items"] if i["id"] == item["id"])
    assert paired_item["chat_session_id"] == chat["id"]


def test_spawn_paired_chat_inherits_parent_tags(client: TestClient) -> None:
    tag_a = client.post("/api/tags", json={"name": "from-parent"}).json()["id"]
    cl, item = _create_checklist_with_item(client, tag_ids=[tag_a])
    resp = client.post(
        f"/api/sessions/{cl['id']}/checklist/items/{item['id']}/chat",
        json={},
    )
    assert resp.status_code == 201
    chat_id = resp.json()["id"]
    chat_tags = client.get(f"/api/sessions/{chat_id}/tags").json()
    assert [t["id"] for t in chat_tags] == [tag_a]


def test_spawn_paired_chat_is_idempotent(client: TestClient) -> None:
    """Double-clicking "Work on this" must return the same session, not
    create a second one. First spawn wins."""
    cl, item = _create_checklist_with_item(client)
    first = client.post(
        f"/api/sessions/{cl['id']}/checklist/items/{item['id']}/chat",
        json={},
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/sessions/{cl['id']}/checklist/items/{item['id']}/chat",
        json={},
    )
    # Second call may return 201 (FastAPI decorator) but with the same
    # session id — idempotency is about the *resource*, not the status.
    assert second.json()["id"] == first.json()["id"]


def test_spawn_paired_chat_rejects_chat_parent(client: TestClient) -> None:
    tag_id = _default_tag(client)
    chat_parent = client.post(
        "/api/sessions",
        json={
            "working_dir": "/tmp",
            "model": "claude-sonnet-4-6",
            "tag_ids": [tag_id],
        },
    ).json()
    resp = client.post(
        f"/api/sessions/{chat_parent['id']}/checklist/items/1/chat",
        json={},
    )
    assert resp.status_code == 400


def test_spawn_paired_chat_404s_on_foreign_item(client: TestClient) -> None:
    """Item id belongs to a different checklist → 404 (defense in depth)."""
    cl_a, _item_a = _create_checklist_with_item(client)
    _cl_b, item_b = _create_checklist_with_item(client)
    resp = client.post(
        f"/api/sessions/{cl_a['id']}/checklist/items/{item_b['id']}/chat",
        json={},
    )
    assert resp.status_code == 404


def test_get_paired_chat_returns_404_when_unpaired(client: TestClient) -> None:
    cl, item = _create_checklist_with_item(client)
    resp = client.get(f"/api/sessions/{cl['id']}/checklist/items/{item['id']}/chat")
    assert resp.status_code == 404


def test_get_paired_chat_returns_session_when_paired(client: TestClient) -> None:
    cl, item = _create_checklist_with_item(client)
    spawn = client.post(
        f"/api/sessions/{cl['id']}/checklist/items/{item['id']}/chat",
        json={},
    ).json()
    resp = client.get(f"/api/sessions/{cl['id']}/checklist/items/{item['id']}/chat")
    assert resp.status_code == 200
    assert resp.json()["id"] == spawn["id"]


def test_spawn_paired_chat_respects_title_override(client: TestClient) -> None:
    cl, item = _create_checklist_with_item(client, label="default label")
    resp = client.post(
        f"/api/sessions/{cl['id']}/checklist/items/{item['id']}/chat",
        json={"title": "custom chat title"},
    )
    assert resp.status_code == 201
    assert resp.json()["title"] == "custom chat title"


def test_spawn_paired_chat_overrides_working_dir_and_model(client: TestClient) -> None:
    cl, item = _create_checklist_with_item(client)
    resp = client.post(
        f"/api/sessions/{cl['id']}/checklist/items/{item['id']}/chat",
        json={"working_dir": "/elsewhere", "model": "claude-opus-4-7"},
    )
    assert resp.status_code == 201
    chat = resp.json()
    assert chat["working_dir"] == "/elsewhere"
    assert chat["model"] == "claude-opus-4-7"
