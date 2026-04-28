"""Paste-into-message lifecycle integration test.

Per ``docs/behavior/vault.md`` §"Paste-into-message behavior" the vault
feeds the active chat composer in three ways:

* **Drag** a vault row → composer receives ``[Title](file:///abs/path)``.
* **Right-click → Copy as Markdown link** → same string on clipboard.
* **Right-click → Copy doc body** → full markdown body to clipboard.

The server-side surface that supports all three is:

1. ``GET /api/vault`` returns each row with a server-computed
   ``markdown_link`` field — the client just inserts that string at
   the cursor.
2. ``GET /api/vault/{id}`` returns the full raw body for the "copy
   doc body" path.

This file walks the lifecycle end-to-end on a synthetic vault and
asserts the resulting message-composer payload matches vault.md's
spec verbatim.

References:

* ``docs/behavior/vault.md`` §"Paste-into-message behavior".
* ``docs/behavior/chat.md`` §"Composer surface" — the composer reads
  the inserted text and emits it as the user message; the server's
  job ends at returning the link string.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from bearings.config.settings import VaultCfg
from bearings.db import get_connection_factory, load_schema
from bearings.web.app import create_app

_HEARTBEAT_S: Final[float] = 5.0


@pytest.fixture
def composer_vault(tmp_path: Path) -> Path:
    """Single-plan vault with a clear title + identifiable body."""
    plans = tmp_path / "plans"
    plans.mkdir()
    (plans / "important-plan.md").write_text(
        "# Important Plan\n\nThis is the doc body.\nLine two.\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def app_client(
    composer_vault: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[TestClient]:
    db_dir = tmp_path_factory.mktemp("dbdir")
    db_path = db_dir / "paste.db"
    cfg = VaultCfg(plan_roots=(composer_vault / "plans",), todo_globs=())

    async def _open() -> aiosqlite.Connection:
        factory = get_connection_factory(db_path)
        conn = await factory()
        await load_schema(conn)
        return conn

    loop = asyncio.new_event_loop()
    try:
        conn = loop.run_until_complete(_open())
        app = create_app(
            heartbeat_interval_s=_HEARTBEAT_S,
            db_connection=conn,
            vault_cfg=cfg,
        )
        with TestClient(app) as client:
            yield client
        loop.run_until_complete(conn.close())
    finally:
        loop.close()


def test_drag_paste_lifecycle_yields_markdown_link(
    app_client: TestClient, composer_vault: Path
) -> None:
    """Listing → grabbing the markdown_link → composer inserts the link."""
    listed = app_client.get("/api/vault").json()
    assert len(listed["plans"]) == 1
    row = listed["plans"][0]

    abs_path = str((composer_vault / "plans" / "important-plan.md").resolve(strict=True))
    expected_link = f"[Important Plan](file://{abs_path})"
    # Per vault.md the drag/copy-link both produce this exact string.
    assert row["markdown_link"] == expected_link

    # Simulate the chat composer inserting the link into a draft message.
    composer_draft_before = "see this: "
    composer_draft_after = composer_draft_before + row["markdown_link"]
    assert "[Important Plan](file://" in composer_draft_after
    assert composer_draft_after.endswith("/important-plan.md)")


def test_copy_doc_body_lifecycle_returns_full_body(
    app_client: TestClient,
) -> None:
    """Right-click → "Copy doc body" reads the body via GET /{id}."""
    listed = app_client.get("/api/vault").json()
    plan_id = listed["plans"][0]["id"]

    response = app_client.get(f"/api/vault/{plan_id}")
    assert response.status_code == 200
    body = response.json()

    # The full markdown is available for clipboard copy verbatim.
    assert "# Important Plan" in body["body"]
    assert "This is the doc body." in body["body"]
    assert "Line two." in body["body"]


def test_id_remains_stable_across_rescan(app_client: TestClient) -> None:
    """A paste-link follow-up open uses the original id; rescans must preserve it.

    Per ``bearings.db.vault`` the upsert-by-path discipline keeps ``id``
    constant across rescans so a click on a previously-pasted link
    still resolves to the same doc.
    """
    first = app_client.get("/api/vault").json()
    original_id = first["plans"][0]["id"]
    # Rescan via second list call — id must persist.
    second = app_client.get("/api/vault").json()
    assert second["plans"][0]["id"] == original_id
    # Open by the original id still works.
    response = app_client.get(f"/api/vault/{original_id}")
    assert response.status_code == 200


def test_link_path_resolves_via_by_path_endpoint(
    app_client: TestClient, composer_vault: Path
) -> None:
    """Linkifier click in chat → resolves via /by-path → opens in vault pane."""
    listed = app_client.get("/api/vault").json()
    row = listed["plans"][0]
    # Simulate the linkifier extracting the path from the markdown link.
    link = row["markdown_link"]
    # `[Title](file:///abs/path)` → strip prefix/suffix
    abs_path = link.split("](file://", 1)[1].rstrip(")")
    response = app_client.get("/api/vault/by-path", params={"path": abs_path})
    assert response.status_code == 200
    assert response.json()["entry"]["slug"] == "important-plan"
