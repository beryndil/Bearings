"""Avatar upload / serve / clear for the singleton preferences row.

Split from `routes_preferences.py` so the avatar pipeline (Pillow
import, multipart handling, byte-streaming response) doesn't bloat the
plain GET/PATCH module past the 400-line ceiling.

Storage shape (migration 0035): the bytes live at
`Settings.storage.avatar_path` (default `<DATA_HOME>/avatar.png`),
always normalised to a 512×512 PNG by Pillow regardless of the upload
format. The DB tracks `avatar_uploaded_at` only; that timestamp is the
cache-busting key the frontend embeds in `?v=`.

Three endpoints:

* `POST /api/preferences/avatar` — multipart upload, validates MIME,
  enforces the byte cap while reading, runs the resize pipeline, and
  bumps `avatar_uploaded_at`. Returns the updated `PreferencesOut`.
* `DELETE /api/preferences/avatar` — unlinks the file (idempotent),
  nulls `avatar_uploaded_at`. Returns the updated row.
* `GET /api/preferences/avatar` — streams the PNG with an ETag keyed
  on `avatar_uploaded_at`. 404 when unset; 304 on If-None-Match match.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image, UnidentifiedImageError

from bearings.api.auth import require_auth
from bearings.api.models import PreferencesOut
from bearings.db import store

router = APIRouter(
    prefix="/preferences/avatar",
    tags=["preferences"],
    dependencies=[Depends(require_auth)],
)

# Browsers serve the same image set with these MIME types reliably.
# Anything else (HEIC, AVIF, GIF) is rejected with 415 — we'd rather
# the user pick a format Pillow's stable decoders cover than ship a
# half-decoded surprise into the sidebar.
_ALLOWED_MIME = frozenset({"image/png", "image/jpeg", "image/webp"})

# Streaming chunk size for the size-cap loop. 1 MiB matches
# routes_uploads.py — same trade-off between syscall overhead and
# bounded memory under a lying Content-Length.
_CHUNK_SIZE = 1 << 20

# Output square edge in pixels. 512 is the size used by the greetd
# AccountsService avatar contract Bearings mirrors at the system
# layer, so the source asset is sized right and the sidebar can
# render at any device-pixel ratio without resampling jaggies.
_AVATAR_EDGE_PX = 512

# Pillow's resize quality. LANCZOS is the right pick for downscale —
# the upload is almost always larger than 512 and bicubic would soften
# the chunky-pixel look the Minecraft-style portrait depends on.
_RESIZE_FILTER = Image.Resampling.LANCZOS


def _strip_id(row: dict[str, Any]) -> dict[str, Any]:
    """Drop the singleton `id=1` from the row before it crosses the
    wire. Mirrors the helper in routes_preferences.py — kept private
    here so this module doesn't reach into the sibling route file just
    for one trivially short function."""
    return {k: v for k, v in row.items() if k != "id"}


def _now_iso() -> str:
    """ISO-8601 UTC timestamp matching the format `_common._now` emits
    elsewhere. Used as the cache-busting key in `avatar_uploaded_at`.
    Re-implemented here rather than imported because the DB internals
    package is private to the store layer."""
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "+00:00")


async def _read_with_cap(file: UploadFile, max_bytes: int) -> bytes:
    """Read the upload into memory, enforcing the byte cap as bytes
    arrive. Returns the buffered bytes for Pillow to decode in-memory.

    Avatars are bounded (5 MiB cap by default) — buffering is fine and
    Pillow needs random access to the input anyway. A streaming-
    decode path would buy nothing here.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"avatar exceeds {max_bytes // (1024 * 1024)} MiB limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _normalise_to_png(raw: bytes, dest: Path) -> None:
    """Decode `raw`, center-crop to a square, resize to 512×512, save
    as PNG at `dest`. Atomic-ish via write-to-temp + replace so a half-
    written file never lands at the served path even if Pillow raises
    mid-encode.

    The crop is deliberately centered rather than face-detected: the
    feature is single-user and Dave can crop ahead of time if his
    chosen image needs it. Adding ML deps for a one-user UX is the
    wrong trade.
    """
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.load()  # force decode now so we surface errors here
            converted = img.convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=415, detail="unable to decode image") from exc

    width, height = converted.size
    edge = min(width, height)
    left = (width - edge) // 2
    top = (height - edge) // 2
    cropped = converted.crop((left, top, left + edge, top + edge))
    resized = cropped.resize((_AVATAR_EDGE_PX, _AVATAR_EDGE_PX), _RESIZE_FILTER)

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        resized.save(tmp, format="PNG", optimize=True)
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)


@router.post("", response_model=PreferencesOut)
async def upload_avatar(request: Request, file: UploadFile) -> PreferencesOut:
    """Accept an image upload, normalise it to a 512×512 PNG, and bump
    `avatar_uploaded_at`. The byte cap is enforced while reading; MIME
    is checked before any bytes hit Pillow.
    """
    cfg = request.app.state.settings.storage
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"MIME {content_type or 'unknown'} not in {sorted(_ALLOWED_MIME)}",
        )

    max_bytes = cfg.avatar_max_size_mb * 1024 * 1024
    raw = await _read_with_cap(file, max_bytes)
    _normalise_to_png(raw, Path(cfg.avatar_path))

    row = await store.update_preferences(request.app.state.db, avatar_uploaded_at=_now_iso())
    return PreferencesOut(**_strip_id(row))


@router.delete("", response_model=PreferencesOut)
async def delete_avatar(request: Request) -> PreferencesOut:
    """Clear the avatar — unlink the file and null the DB column.
    Idempotent: a delete with nothing to delete is a no-op success,
    same as DELETE on a missing checkpoint elsewhere in the API.
    """
    cfg = request.app.state.settings.storage
    Path(cfg.avatar_path).unlink(missing_ok=True)
    row = await store.update_preferences(request.app.state.db, avatar_uploaded_at=None)
    return PreferencesOut(**_strip_id(row))


@router.get("")
async def get_avatar(request: Request) -> Response:
    """Stream the avatar PNG. Returns 404 when no avatar is set so the
    frontend can fall back to the initials renderer; the call is cheap
    and unconditional so the sidebar doesn't have to gate it on a
    preferences-row inspection.

    `ETag` is keyed on `avatar_uploaded_at` (the same timestamp the
    cache-busted URL embeds). When the client sends `If-None-Match`
    matching the current ETag we return 304 with no body — the bytes
    on disk haven't changed and the browser cache is authoritative.
    """
    row = await store.get_preferences(request.app.state.db)
    uploaded_at = row.get("avatar_uploaded_at")
    avatar_path = Path(request.app.state.settings.storage.avatar_path)
    if not uploaded_at or not avatar_path.is_file():
        raise HTTPException(status_code=404, detail="no avatar set")

    etag = f'"{uploaded_at}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return FileResponse(
        path=str(avatar_path),
        media_type="image/png",
        headers={
            "ETag": etag,
            "Cache-Control": "private, max-age=0, must-revalidate",
        },
    )
