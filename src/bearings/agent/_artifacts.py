"""Auto-register agent-written image artifacts for inline display.

Phase 1 of the File Display feature (linked Bearings session
edaae9bad976411a86e8674665a3dac4): when the SDK's `Write` tool
successfully writes an image-MIME file under
`settings.artifacts.serve_roots`, this hook registers an artifact row
and returns a markdown image reference that the turn executor injects
into the assistant's reply. The existing markdown renderer already
allows `<img>` with `src=/api/artifacts/{id}` (verified via
`frontend/src/lib/render.ts`'s sanitize config), so injection alone is
enough to render inline — no client-side changes.

Phase 1 holds the line on stdlib only: `mimetypes`, `hashlib`,
`pathlib`. python-docx / openpyxl / reportlab / weasyprint / Pillow
arrive in Phases 2-4 (deferred to a later checklist item).

Best-effort: any failure (path missing, hash error, DB write blow-up)
is logged and swallowed. The Write tool already succeeded by the time
this hook runs; failing the turn over a missing inline-render side
effect would be worse UX than the missing thumbnail.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from bearings.config import ArtifactsCfg
from bearings.db import store

if TYPE_CHECKING:
    from bearings.agent.runner import SessionRunner

log = logging.getLogger(__name__)

# SHA-256 hash chunk size — matches `routes_artifacts._HASH_CHUNK_BYTES`
# so a path registered via the hook hashes identically to one registered
# via `POST /api/sessions/{sid}/artifacts`. Idempotency hooks (a future
# (session_id, sha256) dedup) will compare digests across both paths.
_HASH_CHUNK_BYTES = 1 << 20


def _is_image_mime(mime_type: str | None) -> bool:
    """True iff the detected MIME starts with `image/`. Phase 1 scope:
    only image artifacts get the auto-register + inline-markdown
    treatment. PDF/DOCX/XLSX previews live in Phases 3-4 behind the
    FilePreview component and aren't auto-injected as `<img>`."""
    return bool(mime_type and mime_type.startswith("image/"))


def _resolve_serve_roots(cfg: ArtifactsCfg) -> list[Path]:
    """Resolve the configured roots at the moment of the check, not
    at config load — a symlink that flips between boot and write
    shouldn't grant access to a tree outside the allowlist. Mirrors
    `routes_artifacts._resolve_serve_roots`."""
    return [Path(root).resolve(strict=False) for root in cfg.serve_roots]


def _path_under_allowlist(candidate: Path, roots: list[Path]) -> bool:
    """True iff `candidate` (already resolved) lives under at least
    one resolved root. `is_relative_to` returns False on mismatch."""
    return any(candidate.is_relative_to(root) for root in roots)


def _hash_and_size(path: Path) -> tuple[str, int]:
    """Stream `path` through SHA-256 and tally bytes. Same one-pass
    contract as the HTTP register path so the persisted row pins the
    bytes that existed at write time."""
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _write_path_from_input(tool_input: Mapping[str, object]) -> str | None:
    """Pull the path argument out of the SDK's Write-tool input dict.

    The SDK's `Write` tool emits `file_path`; older transcripts and
    some MCP servers emit `path`. Accept both, but only return when the
    value is a non-empty string — anything else (None, dict, bytes)
    is treated as a non-Write or malformed payload."""
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


async def maybe_auto_register_image_artifact(
    runner: SessionRunner,
    *,
    tool_name: str,
    tool_input: Mapping[str, object],
    ok: bool,
) -> str | None:
    """Register an image artifact if the just-finished tool call was a
    successful `Write` to a path under the configured serve roots, and
    return the markdown image to inject into the assistant's reply.

    Returns `None` (and registers nothing) when:
      * the runner has no `ArtifactsCfg` wired (test harness, etc.);
      * the tool isn't `Write`;
      * the tool failed (`ok=False`);
      * the input has no usable path;
      * the resolved path doesn't live under `serve_roots`;
      * the path isn't a regular file on disk;
      * the path's MIME doesn't look like an image;
      * the file exceeds the configured `max_register_size_mb`;
      * any IO / DB error surfaces (logged and swallowed).
    """
    cfg = runner._artifacts_cfg
    if cfg is None:
        return None
    if tool_name != "Write" or not ok:
        return None

    raw_path = _write_path_from_input(tool_input)
    if raw_path is None:
        return None

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        return None
    resolved = candidate.resolve(strict=False)
    if not _path_under_allowlist(resolved, _resolve_serve_roots(cfg)):
        return None
    if not resolved.is_file():
        return None

    mime_type, _ = mimetypes.guess_type(str(resolved))
    if not _is_image_mime(mime_type):
        return None

    max_bytes = cfg.max_register_size_mb * 1024 * 1024
    try:
        if resolved.stat().st_size > max_bytes:
            log.info(
                "auto-register skipped: %s exceeds %d MB cap",
                resolved,
                cfg.max_register_size_mb,
            )
            return None
        digest, hashed_size = _hash_and_size(resolved)
        row = await store.create_artifact(
            runner.db,
            runner.session_id,
            path=str(resolved),
            filename=resolved.name,
            mime_type=mime_type or "application/octet-stream",
            size_bytes=hashed_size,
            sha256=digest,
        )
    except (OSError, ValueError) as exc:
        log.warning(
            "auto-register failed for %s in session %s: %s",
            resolved,
            runner.session_id,
            exc,
        )
        return None
    except Exception:  # noqa: BLE001 — DB drivers raise heterogeneous types
        log.exception(
            "auto-register failed unexpectedly for %s in session %s",
            resolved,
            runner.session_id,
        )
        return None

    # Markdown surrounded by blank lines so the renderer treats it as
    # its own paragraph — without the leading `\n\n` the image would
    # collapse into the preceding sentence and a few markdown engines
    # would render it as inline-with-text rather than block.
    return f"\n\n![{resolved.name}](/api/artifacts/{row['id']})\n"
