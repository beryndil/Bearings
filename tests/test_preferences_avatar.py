"""Coverage for the avatar upload / serve / clear pipeline (migration
0035 + routes_preferences_avatar.py).

Three layers of expectation:

* **Validation** — MIME allowlist (415), byte cap (413), undecodable
  bytes despite a valid MIME header (415). Each reject branch should
  leave `avatar_uploaded_at` NULL and no file at the configured path.
* **Round-trip** — POST a real PNG, the file lands at the configured
  path, the row carries a non-NULL `avatar_uploaded_at`, GET streams
  PNG bytes whose ETag matches the row, and a follow-up GET with
  `If-None-Match` returns 304.
* **Clear** — DELETE unlinks the file (idempotent) and nulls the
  column. A second DELETE is still a 200 with a NULL row, since the
  feature is "make it not visible," not "fail loudly when nothing's
  there."

`tmp_settings` already redirects `storage.avatar_path` via the
default-factory chain (DATA_HOME → tmp_path is NOT automatic — the
fixture pins `db_path` only). Each test pins `avatar_path` explicitly
through a settings override fixture so the dev's real avatar at
`~/.local/share/bearings/avatar.png` can never be touched.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from bearings.config import Settings
from bearings.server import create_app

# Edge of the synthetic source images. Larger than 512 so the resize
# pipeline actually downscales (matches the "user uploads a bigger
# image" expected case); not so large the byte cap kicks in.
_SOURCE_EDGE_PX = 800

# The route normalises every accepted upload to this edge. Mirrors
# `_AVATAR_EDGE_PX` in routes_preferences_avatar.py — kept as a local
# constant rather than imported from the route so a refactor that
# silently changes the contract still trips a test.
_EXPECTED_EDGE_PX = 512


@pytest.fixture
def avatar_settings(tmp_settings: Settings, tmp_path: Path) -> Settings:
    """Pin the avatar path under tmp_path so uploads can't escape."""
    tmp_settings.storage.avatar_path = tmp_path / "avatar.png"
    # Smaller cap so the oversize test fixture stays cheap to build.
    tmp_settings.storage.avatar_max_size_mb = 1
    return tmp_settings


@pytest.fixture
def avatar_app(avatar_settings: Settings) -> FastAPI:
    return create_app(avatar_settings)


@pytest.fixture
def avatar_client(avatar_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(avatar_app) as c:
        c.headers["origin"] = "http://testserver"
        yield c


def _png_bytes(edge: int = _SOURCE_EDGE_PX, color: tuple[int, int, int] = (200, 80, 60)) -> bytes:
    """Build an in-memory PNG of the requested edge length. Solid
    colour is fine — the test only inspects size and format, not pixel
    content. Returns the encoded bytes ready for multipart upload."""
    img = Image.new("RGB", (edge, edge), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(edge: int = _SOURCE_EDGE_PX) -> bytes:
    img = Image.new("RGB", (edge, edge), (40, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


# --- POST happy path ------------------------------------------------


def test_post_avatar_writes_512_png_and_bumps_timestamp(
    avatar_client: TestClient, avatar_settings: Settings
) -> None:
    payload = _png_bytes()
    res = avatar_client.post(
        "/api/preferences/avatar",
        files={"file": ("portrait.png", payload, "image/png")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["avatar_uploaded_at"] is not None
    assert body["avatar_url"] == f"/api/preferences/avatar?v={body['avatar_uploaded_at']}"

    # The on-disk file is normalised to a 512×512 PNG regardless of
    # source format / size.
    saved = avatar_settings.storage.avatar_path
    assert saved.is_file()
    with Image.open(saved) as img:
        assert img.format == "PNG"
        assert img.size == (_EXPECTED_EDGE_PX, _EXPECTED_EDGE_PX)


def test_post_avatar_accepts_jpeg_and_normalises_to_png(
    avatar_client: TestClient, avatar_settings: Settings
) -> None:
    res = avatar_client.post(
        "/api/preferences/avatar",
        files={"file": ("portrait.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert res.status_code == 200, res.text
    saved = avatar_settings.storage.avatar_path
    with Image.open(saved) as img:
        assert img.format == "PNG"


# --- POST validation ------------------------------------------------


def test_post_avatar_rejects_non_image_mime(
    avatar_client: TestClient, avatar_settings: Settings
) -> None:
    res = avatar_client.post(
        "/api/preferences/avatar",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 415
    assert not avatar_settings.storage.avatar_path.exists()
    # Row stays at NULL — a reject must not advance the timestamp.
    prefs = avatar_client.get("/api/preferences").json()
    assert prefs["avatar_uploaded_at"] is None


def test_post_avatar_rejects_oversize_payload(
    avatar_client: TestClient, avatar_settings: Settings
) -> None:
    # Cap is 1 MiB in the fixture; 2 MiB of zero bytes blows past it
    # before Pillow ever sees the buffer, which is the whole point of
    # the streaming size check.
    cap = avatar_settings.storage.avatar_max_size_mb * 1024 * 1024
    payload = b"\x00" * (cap + 1024)
    res = avatar_client.post(
        "/api/preferences/avatar",
        files={"file": ("huge.png", payload, "image/png")},
    )
    assert res.status_code == 413
    assert not avatar_settings.storage.avatar_path.exists()


def test_post_avatar_rejects_undecodable_bytes(
    avatar_client: TestClient, avatar_settings: Settings
) -> None:
    """A request that lies about its content-type — claims image/png
    but ships garbage — must be rejected with 415, not crash with a
    500 from Pillow."""
    res = avatar_client.post(
        "/api/preferences/avatar",
        files={"file": ("fake.png", b"not actually a png", "image/png")},
    )
    assert res.status_code == 415
    assert not avatar_settings.storage.avatar_path.exists()


# --- GET ------------------------------------------------------------


def test_get_avatar_returns_404_when_unset(avatar_client: TestClient) -> None:
    res = avatar_client.get("/api/preferences/avatar")
    assert res.status_code == 404


def test_get_avatar_streams_png_with_etag(
    avatar_client: TestClient, avatar_settings: Settings
) -> None:
    avatar_client.post(
        "/api/preferences/avatar",
        files={"file": ("portrait.png", _png_bytes(), "image/png")},
    )
    res = avatar_client.get("/api/preferences/avatar")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    etag = res.headers["etag"]
    # ETag is wrapped in double-quotes per RFC 7232.
    assert etag.startswith('"') and etag.endswith('"')

    # Round-trip: If-None-Match → 304 with no body.
    res304 = avatar_client.get("/api/preferences/avatar", headers={"If-None-Match": etag})
    assert res304.status_code == 304
    assert res304.content == b""


# --- DELETE ---------------------------------------------------------


def test_delete_avatar_unlinks_file_and_nulls_column(
    avatar_client: TestClient, avatar_settings: Settings
) -> None:
    avatar_client.post(
        "/api/preferences/avatar",
        files={"file": ("portrait.png", _png_bytes(), "image/png")},
    )
    assert avatar_settings.storage.avatar_path.is_file()

    res = avatar_client.delete("/api/preferences/avatar")
    assert res.status_code == 200
    assert res.json()["avatar_uploaded_at"] is None
    assert res.json()["avatar_url"] is None
    assert not avatar_settings.storage.avatar_path.exists()


def test_delete_avatar_is_idempotent(avatar_client: TestClient) -> None:
    """A clear with nothing to clear is still a 200. Frontend doesn't
    need to gate the call on a row inspection."""
    res = avatar_client.delete("/api/preferences/avatar")
    assert res.status_code == 200
    assert res.json()["avatar_uploaded_at"] is None


# --- Migration / model coverage -------------------------------------


def test_preferences_get_includes_avatar_fields(avatar_client: TestClient) -> None:
    """Pure shape check — every preferences response must carry the
    new `avatar_uploaded_at` and `avatar_url` keys regardless of state.
    Catches the case where a future refactor drops them from the wire
    DTO and the frontend silently never knows the avatar exists."""
    body = avatar_client.get("/api/preferences").json()
    assert "avatar_uploaded_at" in body
    assert "avatar_url" in body
    assert body["avatar_uploaded_at"] is None
    assert body["avatar_url"] is None
