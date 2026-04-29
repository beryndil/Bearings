"""Integration tests for ``bearings.web.routes.uploads`` (item 1.10).

Exercises POST/GET/DELETE happy paths, sha256 dedup, oversize 413,
empty-body 400, and roundtrip persistence via the storage-root.
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from bearings.config.constants import UPLOAD_DEFAULT_MIME_TYPE
from bearings.config.settings import UploadsCfg
from bearings.db import get_connection_factory, load_schema
from bearings.web.app import create_app

_HEARTBEAT_S: Final[float] = 5.0


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    """Boot the app with a fresh DB + sandboxed uploads root."""
    db_path = tmp_path / "uploads.db"
    storage_root = tmp_path / "uploads-store"

    async def _open() -> aiosqlite.Connection:
        factory = get_connection_factory(db_path)
        conn = await factory()
        await load_schema(conn)
        return conn

    loop = asyncio.new_event_loop()
    try:
        conn = loop.run_until_complete(_open())
        cfg = UploadsCfg(storage_root=storage_root, max_size_bytes=1024)
        app = create_app(
            heartbeat_interval_s=_HEARTBEAT_S,
            db_connection=conn,
            uploads_cfg=cfg,
        )
        with TestClient(app) as client:
            yield client, storage_root
        loop.run_until_complete(conn.close())
    finally:
        loop.close()


def test_post_upload_creates_row_and_disk_body(
    app_client: tuple[TestClient, Path],
) -> None:
    client, storage_root = app_client
    body = b"hello uploads"
    response = client.post(
        "/api/uploads",
        files={"file": ("greeting.txt", io.BytesIO(body), "text/plain")},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["filename"] == "greeting.txt"
    assert payload["mime_type"] == "text/plain"
    assert payload["size"] == len(body)
    assert len(payload["sha256"]) == 64
    # On-disk body lands at the canonical shard path.
    sha = payload["sha256"]
    on_disk = storage_root / sha[:2] / sha
    assert on_disk.exists()
    assert on_disk.read_bytes() == body


def test_post_upload_dedup_on_sha256(
    app_client: tuple[TestClient, Path],
) -> None:
    client, _ = app_client
    body = b"identical body"
    first = client.post(
        "/api/uploads",
        files={"file": ("a.txt", io.BytesIO(body), "text/plain")},
    )
    second = client.post(
        "/api/uploads",
        files={"file": ("b.txt", io.BytesIO(body), "text/plain")},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["sha256"] == second.json()["sha256"]


def test_post_upload_413_on_oversize(
    app_client: tuple[TestClient, Path],
) -> None:
    client, _ = app_client
    # Cap is 1024 bytes per the fixture's UploadsCfg.
    body = b"x" * 2048
    response = client.post(
        "/api/uploads",
        files={"file": ("big.bin", io.BytesIO(body), "application/octet-stream")},
    )
    assert response.status_code == 413


def test_post_upload_400_on_empty_body(
    app_client: tuple[TestClient, Path],
) -> None:
    client, _ = app_client
    response = client.post(
        "/api/uploads",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert response.status_code == 400


def test_get_uploads_lists_newest_first(
    app_client: tuple[TestClient, Path],
) -> None:
    client, _ = app_client
    client.post("/api/uploads", files={"file": ("a.txt", io.BytesIO(b"first"))})
    client.post("/api/uploads", files={"file": ("b.txt", io.BytesIO(b"second"))})
    response = client.get("/api/uploads")
    assert response.status_code == 200
    rows = response.json()["uploads"]
    assert len(rows) == 2
    # Newest row comes first.
    assert rows[0]["filename"] == "b.txt"


def test_get_upload_content_streams_body(
    app_client: tuple[TestClient, Path],
) -> None:
    client, _ = app_client
    body = b"streamable bytes"
    posted = client.post(
        "/api/uploads",
        files={"file": ("c.bin", io.BytesIO(body), "image/png")},
    )
    upload_id = posted.json()["id"]
    response = client.get(f"/api/uploads/{upload_id}/content")
    assert response.status_code == 200
    assert response.content == body
    assert response.headers["content-type"].startswith("image/png")


def test_delete_upload_removes_row_and_body(
    app_client: tuple[TestClient, Path],
) -> None:
    client, storage_root = app_client
    posted = client.post(
        "/api/uploads",
        files={"file": ("d.txt", io.BytesIO(b"to-delete"))},
    )
    upload_id = posted.json()["id"]
    sha = posted.json()["sha256"]
    response = client.delete(f"/api/uploads/{upload_id}")
    assert response.status_code == 204
    assert not (storage_root / sha[:2] / sha).exists()
    assert client.get(f"/api/uploads/{upload_id}").status_code == 404


def test_get_upload_404_when_missing(
    app_client: tuple[TestClient, Path],
) -> None:
    client, _ = app_client
    assert client.get("/api/uploads/9999").status_code == 404
    assert client.delete("/api/uploads/9999").status_code == 404


def test_post_upload_falls_back_to_octet_stream_mime(
    app_client: tuple[TestClient, Path],
) -> None:
    client, _ = app_client
    # No explicit content-type → FastAPI's UploadFile.content_type is
    # ``application/octet-stream``-ish. Our route normalises absent
    # content-type to UPLOAD_DEFAULT_MIME_TYPE.
    response = client.post(
        "/api/uploads",
        files={"file": ("plain", io.BytesIO(b"plain"))},
    )
    assert response.status_code == 201
    assert response.json()["mime_type"] in (
        UPLOAD_DEFAULT_MIME_TYPE,
        "application/octet-stream",
    )
