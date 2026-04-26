"""File upload bridge for browser drag-and-drop.

Chrome on Wayland strips the `text/uri-list` path metadata from file
drops even though `DataTransfer.files` still carries the bytes. The
frontend reads those bytes, POSTs them here, and the server persists
them under the configured upload directory. The resulting absolute
path is injected into the prompt — Claude reads the file from disk
exactly as if the user had typed the path by hand.

Layout: `<upload_dir>/<uuid>/<sanitized-original-name.ext>`. Each
upload gets a fresh UUID subdirectory and keeps the original filename
inside it. This gives us three things at once:

  1. **Traversal safety.** The UUID directory is server-generated, so
     the only user-controlled path segment is the innermost filename,
     and we scrub it to a single path component (no separators, no
     control chars, capped length).
  2. **Collision resistance.** Two drops of `screenshot.png` land in
     different UUID dirs, so neither overwrites the other.
  3. **Legible paths.** The prompt-injected path ends with the real
     filename, so Claude (and the user reading the transcript) can
     tell at a glance what was dropped — instead of a 32-char UUID.

Security posture: Bearings is localhost/single-user. The endpoint
accepts any file up to the configured size cap; a short extension
blocklist rejects shell scripts and binaries as defense-in-depth
(Claude has no business being handed those via a drag gesture, and
the rare legitimate case can go through the native picker instead).

No transcript persistence in v1 — the uploaded file's path is the
whole UX. GC is deferred; see TODO.md.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from bearings.api.auth import require_auth
from bearings.api.models import UploadOut

router = APIRouter(
    prefix="/uploads",
    tags=["uploads"],
    dependencies=[Depends(require_auth)],
)

# Only `.xxx` where `xxx` is alphanumeric and ≤16 chars is preserved.
# Anything weirder (multi-dot, unicode, punctuation) is dropped — if
# the original filename had a genuinely useful extension it'll still
# match this shape, and if it didn't, the file is saved without one
# rather than with a malformed suffix that trips downstream tools.
_EXT_ALLOWED_SHAPE = re.compile(r"^\.[A-Za-z0-9]{1,16}$")

_DEFAULT_MIME = "application/octet-stream"

# Streaming chunk size for the size-cap loop. 1 MiB balances syscall
# overhead against the max memory a single read holds. The cap is
# enforced as bytes arrive so a client that lies about Content-Length
# still hits the limit in bounded memory.
_CHUNK_SIZE = 1 << 20

# Cap on the sanitized filename stem (before extension). Long enough
# to preserve ordinary filenames, short enough that a pathological
# input can't blow up path buffers downstream. 200 chars matches the
# practical basename limit on ext4/btrfs once the UUID dir and the
# extension are accounted for.
_FILENAME_STEM_MAX = 200


def _sanitize_stem(stem: str) -> str:
    """Scrub a filename stem for use as the innermost path segment.

    Replaces path separators and non-printable characters with `_`,
    collapses whitespace runs, strips leading/trailing whitespace,
    caps length, and falls back to `upload` on empty input. The UUID
    subdirectory above it is the real traversal boundary; this
    function's job is just to keep the on-disk name tidy and the
    injected path copy-pasteable.
    """
    cleaned = "".join(c if c.isprintable() and c not in "/\\" else "_" for c in stem)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned[:_FILENAME_STEM_MAX]
    return cleaned or "upload"


def _safe_extension(filename: str, blocked: set[str]) -> str:
    """Extract the extension from `filename`. Returns the lowercased
    suffix (including the leading dot) when it's a safe shape AND not
    in the blocklist; otherwise returns an empty string.

    `Path(filename).suffix` neutralises traversal payloads — even if
    `filename` is `../../etc/passwd.sh`, `suffix` is just `.sh`, and
    we only ever consult the suffix. The on-disk name never uses any
    other part of the user-supplied filename.
    """
    suffix = Path(filename).suffix
    if not suffix:
        return ""
    if not _EXT_ALLOWED_SHAPE.match(suffix):
        return ""
    lowered = suffix.lower()
    if lowered in blocked:
        return ""
    return lowered


async def _persist_upload(file: UploadFile, cfg: object) -> UploadOut:
    """Write a single `UploadFile` to disk and return its `UploadOut`.

    Extracted from `upload_file` so the batch endpoint can reuse the
    exact same enforcement order without duplicating the size-cap +
    blocklist + allowlist + sanitize + UUID-subdir + cleanup logic.
    `cfg` is duck-typed `UploadsCfg`; the typing module isn't imported
    to keep this helper independent of pydantic settings internals.

    Behaviour matches the single-file endpoint's contract verbatim —
    every reject branch raises the same `HTTPException` (413 / 415 /
    500) so the batch caller can let exceptions propagate and FastAPI
    serialises one error per fail-fast batch the same as a solo POST.
    """
    max_bytes = cfg.max_size_mb * 1024 * 1024  # type: ignore[attr-defined]
    blocked = {e.lower() for e in cfg.blocked_extensions}  # type: ignore[attr-defined]

    original_name = file.filename or "upload"
    requested_suffix = Path(original_name).suffix
    ext = _safe_extension(original_name, blocked)

    # Differentiate "had no extension, don't need one" (accept,
    # save without a suffix) from "had an extension we refused"
    # (reject with 415 so the caller knows why). Silently stripping
    # a blocked extension would land the file on disk with a
    # misleading name, which is the exact failure mode the blocklist
    # exists to prevent.
    if requested_suffix and not ext:
        raise HTTPException(
            status_code=415,
            detail=f"extension not allowed: {requested_suffix}",
        )

    allowed_mime = {m.lower() for m in cfg.allowed_mime_types}  # type: ignore[attr-defined]
    if allowed_mime:
        allowed_ext = {e.lower() for e in cfg.allowed_extensions}  # type: ignore[attr-defined]
        content_type = (file.content_type or "").lower()
        # Match by MIME or by extension; either is sufficient.
        ext_ok = bool(ext) and ext in allowed_ext
        mime_ok = content_type in allowed_mime
        if not (ext_ok or mime_ok):
            raise HTTPException(
                status_code=415,
                detail=(
                    f"MIME {content_type or 'unknown'} not in allowlist "
                    f"and extension {requested_suffix or '(none)'} not allowed"
                ),
            )

    # Build the on-disk filename: sanitized stem + normalized ext.
    # `Path.name` strips any path components from the user-supplied
    # name (so `../../etc/passwd.txt` becomes `passwd.txt` before we
    # even sanitize), and `_sanitize_stem` handles the rest.
    basename = Path(original_name).name or "upload"
    stem = Path(basename).stem or "upload"
    safe_name = f"{_sanitize_stem(stem)}{ext}"

    # UUID subdirectory under the upload root. Fresh per call so two
    # drops of the same filename don't collide, and server-generated
    # so the traversal surface is limited to `safe_name` — which can
    # only be a single path component by construction.
    upload_dir = Path(cfg.upload_dir)  # type: ignore[attr-defined]
    dest_dir = upload_dir / uuid.uuid4().hex
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_name

    size = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"file exceeds {cfg.max_size_mb} MB limit",  # type: ignore[attr-defined]
                    )
                out.write(chunk)
    except HTTPException:
        # Don't leave half-written rejects on disk — the caller sees
        # an error and will not retry with the server path. Remove
        # the UUID dir too so a stream of over-size rejects doesn't
        # litter the upload root with empty directories.
        dest.unlink(missing_ok=True)
        dest_dir.rmdir() if dest_dir.exists() and not any(dest_dir.iterdir()) else None
        raise
    except OSError as exc:
        dest.unlink(missing_ok=True)
        dest_dir.rmdir() if dest_dir.exists() and not any(dest_dir.iterdir()) else None
        raise HTTPException(status_code=500, detail="failed to persist upload") from exc

    return UploadOut(
        path=str(dest),
        filename=safe_name,
        size_bytes=size,
        mime_type=file.content_type or _DEFAULT_MIME,
    )


@router.post("", response_model=UploadOut)
async def upload_file(request: Request, file: UploadFile) -> UploadOut:
    """Persist the uploaded bytes under the configured upload dir and
    return the absolute path. Size cap is enforced while reading so a
    client that lies about Content-Length can't blow up server memory.

    The route auto-creates the upload directory on first call (XDG
    data home by default). Enforcement order: extension check first
    (cheap, rejects before any bytes land on disk), then streaming
    write with a size cap that tears down the partial file on reject.

    Phase 14 (plan §8.5) added an opt-in MIME allowlist on top of the
    legacy denylist. When `uploads.allowed_mime_types` is non-empty,
    a request whose `Content-Type` is NOT in that list AND whose
    lowercased extension is NOT in `allowed_extensions` is rejected
    with 415 — the per-extension fallback exists because browsers
    serve many code files as `application/octet-stream`. Empty list
    keeps the legacy behaviour for installs that haven't set the
    allowlist.
    """
    return await _persist_upload(file, request.app.state.settings.uploads)


class UploadBatchOut(BaseModel):
    """Response for `POST /api/uploads/batch`. `uploads` carries one
    `UploadOut` per file in the request, in the same order the files
    arrived. The frontend's drop pipeline relies on that ordering to
    inject `[File N]` tokens at the cursor in the same sequence the
    user dropped them — a re-ordered list would scramble the prompt."""

    uploads: list[UploadOut]


@router.post("/batch", response_model=UploadBatchOut)
async def upload_batch(
    request: Request,
    files: list[UploadFile] = File(default_factory=list),  # noqa: B008 — FastAPI pattern
) -> UploadBatchOut:
    """Persist multiple files in one round-trip and return them all.

    The single-file route already does a clean job for a one-file
    drop — this endpoint exists for multi-file drops where the
    frontend was previously serial-awaiting N requests just to keep
    injection order deterministic. Batching trades N round-trips for
    one and gives the operator a single progress arc instead of N
    flickers.

    Fail-fast semantics: the first file that violates a guard (size
    cap, blocked extension, MIME allowlist, disk error) raises and
    earlier successes stay on disk. Mirroring the single-file route,
    failures don't roll back successful peers — the client surfaces
    the reject via its diagnostic banner and the user can retry the
    survivors. Tearing down committed peers would also leak a window
    where a half-applied batch's prefix is on disk before the rollback
    walks; cleaner to commit per-file and let the client decide.

    Empty list returns 400 — a zero-file batch is a client bug, not
    a no-op success path.
    """
    if not files:
        raise HTTPException(status_code=400, detail="batch must contain at least one file")
    cfg = request.app.state.settings.uploads
    results: list[UploadOut] = []
    for file in files:
        results.append(await _persist_upload(file, cfg))
    return UploadBatchOut(uploads=results)
