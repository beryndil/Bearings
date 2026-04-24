"""Tests for the `/api/uploads` bytes-upload bridge.

The endpoint is the bytes-side counterpart to `/api/fs/pick`: the
browser drag-and-drop path hands us bytes without a filesystem path
(Chrome/Wayland strips the URI metadata), so the server persists the
bytes under the configured upload directory and hands the absolute
path back for prompt injection.

Layout: `<upload_dir>/<uuid>/<sanitized-original-name.ext>`. Each
upload gets a fresh UUID subdirectory (collision + traversal boundary)
and keeps the original filename inside it so the injected path reads
as something recognizable.

These tests use the `client` + `tmp_settings` fixtures from conftest,
which re-point the upload dir at a tmp_path so the real
`~/.local/share/bearings/uploads` is never touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bearings.config import Settings


def _uploads_dir(tmp_settings: Settings) -> Path:
    """Resolve the active upload dir from settings. Declared here so
    the tests don't hard-code the tmp_path layout — one change to the
    fixture and every test still reads from the right place."""
    return Path(tmp_settings.uploads.upload_dir)


def test_upload_small_text_file_persists_and_returns_path(
    client: TestClient, tmp_settings: Settings
) -> None:
    """Happy path. A small text file uploads cleanly; the response
    carries the absolute on-disk path and metadata, and the bytes
    are readable at that path. The injected path now ends with the
    original filename inside a UUID subdirectory.
    """
    body = b"hello from the drop handler\n"
    resp = client.post(
        "/api/uploads",
        files={"file": ("note.txt", body, "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["filename"] == "note.txt"
    assert payload["size_bytes"] == len(body)
    assert payload["mime_type"] == "text/plain"
    dest = Path(payload["path"])
    assert dest.name == "note.txt"
    # Parent is the UUID subdir, grandparent is the configured root.
    assert dest.parent.parent == _uploads_dir(tmp_settings)
    assert dest.suffix == ".txt"
    assert dest.read_bytes() == body


def test_upload_two_files_generates_unique_names(
    client: TestClient, tmp_settings: Settings
) -> None:
    """Two uploads of the same original filename must not collide —
    each upload gets its own UUID subdir, so two drops of
    `screenshot.png` land in distinct directories and the original
    filename is preserved in both."""
    first = client.post(
        "/api/uploads",
        files={"file": ("screenshot.png", b"aaaa", "image/png")},
    ).json()
    second = client.post(
        "/api/uploads",
        files={"file": ("screenshot.png", b"bbbb", "image/png")},
    ).json()
    assert first["path"] != second["path"]
    # Same basename inside different UUID parents.
    assert Path(first["path"]).name == Path(second["path"]).name == "screenshot.png"
    assert Path(first["path"]).parent != Path(second["path"]).parent
    assert Path(first["path"]).read_bytes() == b"aaaa"
    assert Path(second["path"]).read_bytes() == b"bbbb"


def test_upload_auto_creates_upload_dir(client: TestClient, tmp_settings: Settings) -> None:
    """First call lands before the dir exists. Route must create it
    so a fresh install doesn't need a setup step."""
    target = _uploads_dir(tmp_settings)
    assert not target.exists()
    resp = client.post(
        "/api/uploads",
        files={"file": ("hello.txt", b"ok", "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    assert target.is_dir()


def test_upload_rejects_over_size_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file larger than `max_size_mb` is rejected with 413 and the
    partial write is cleaned up. We shrink the cap via monkeypatch so
    the test doesn't have to ship a 25 MiB fixture."""
    # Cap of 1 MiB keeps the test payload small; chunked write picks
    # up the overrun on the second 1 MiB chunk.
    from bearings.api import routes_uploads

    # Override the setting on the already-constructed app. The handler
    # reads cfg fresh on every call, so patching the attribute is
    # enough without rebuilding the app.
    app = client.app
    app.state.settings.uploads.max_size_mb = 1  # type: ignore[attr-defined]

    payload = b"x" * (2 * 1024 * 1024)  # 2 MiB — double the cap
    resp = client.post(
        "/api/uploads",
        files={"file": ("big.bin", payload, "application/octet-stream")},
    )
    assert resp.status_code == 413
    assert "1 MB" in resp.json()["detail"]
    # And nothing — neither the partial file nor the empty UUID dir —
    # was left on disk for the reject.
    root = _uploads_dir(app.state.settings)  # type: ignore[attr-defined]
    leftovers = list(root.rglob("*")) if root.exists() else []
    assert leftovers == [], f"reject should clean up, found: {leftovers}"
    # Silence unused-import warning for the module we patched through.
    assert routes_uploads is not None


def test_upload_rejects_blocked_extension(client: TestClient) -> None:
    """A `.sh` drop is refused with 415 — extension is blocked. The
    caller gets a readable error rather than a silent extension strip
    that lands a shell script in the upload dir with a misleading name.
    """
    resp = client.post(
        "/api/uploads",
        files={"file": ("owned.sh", b"#!/bin/sh\necho hi\n", "text/x-shellscript")},
    )
    assert resp.status_code == 415
    assert ".sh" in resp.json()["detail"]


def test_upload_rejects_malformed_extension(client: TestClient) -> None:
    """Weird extensions (spaces, punctuation, ludicrous length) fall
    outside the allowed shape. Same 415 branch as the blocklist —
    either way the original extension is not usable and the caller
    should be told."""
    resp = client.post(
        "/api/uploads",
        files={"file": ("thing.this-is-not-an-extension", b"x", "text/plain")},
    )
    assert resp.status_code == 415


def test_upload_file_without_extension_works(client: TestClient, tmp_settings: Settings) -> None:
    """An unextended filename saves without a suffix. We don't invent
    one from the content-type — keeping the suffix tied strictly to
    the user-supplied name means no surprise renames."""
    resp = client.post(
        "/api/uploads",
        files={"file": ("Makefile", b"all:\n\techo hi\n", "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    dest = Path(resp.json()["path"])
    assert dest.suffix == ""
    assert dest.name == "Makefile"
    assert dest.parent.parent == _uploads_dir(tmp_settings)


def test_upload_strips_path_components_from_filename(
    client: TestClient, tmp_settings: Settings
) -> None:
    """Traversal-style filenames (`../../etc/passwd`) must not escape
    the upload dir. `Path.name` strips the path components to
    `passwd.txt` before the sanitizer ever runs, and the UUID subdir
    is server-generated so there's no user-controlled segment above
    the basename. Asserting both: the file lands under the configured
    root, and the displayable name has no slashes."""
    resp = client.post(
        "/api/uploads",
        files={"file": ("../../etc/passwd.txt", b"nope", "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    dest = Path(body["path"])
    assert dest.parent.parent == _uploads_dir(tmp_settings)
    assert "/" not in body["filename"]
    assert body["filename"] == "passwd.txt"
    assert dest.name == "passwd.txt"


def test_upload_preserves_safe_extension_case_insensitively(
    client: TestClient,
) -> None:
    """`.PNG` should be saved as `.png` — the blocklist and shape
    check are both lowercased, so the on-disk suffix is normalised
    to match. Avoids two valid paths (`.PNG` and `.png`) for the same
    semantic type."""
    resp = client.post(
        "/api/uploads",
        files={"file": ("IMG.PNG", b"\x89PNG...", "image/png")},
    )
    assert resp.status_code == 200, resp.text
    dest = Path(resp.json()["path"])
    assert dest.suffix == ".png"


def test_upload_rejects_uppercase_blocked_extension(client: TestClient) -> None:
    """`.SH` is as dangerous as `.sh`. Blocklist match is case-
    insensitive so a client can't bypass by shouting at the shell."""
    resp = client.post(
        "/api/uploads",
        files={"file": ("owned.SH", b"#!/bin/sh\n", "text/plain")},
    )
    assert resp.status_code == 415


def test_upload_sanitizes_control_chars_and_whitespace(
    client: TestClient, tmp_settings: Settings
) -> None:
    """Filenames with control characters, embedded newlines, or runs
    of whitespace round-trip to a tidy on-disk name. The UUID subdir
    is the real traversal boundary; the sanitizer's job is just to
    keep the injected path copy-pasteable."""
    # NUL byte, tab, and a literal newline in the filename stem.
    # The extension is valid (`.log`) so we keep it.
    weird = "noi\x00sy\tname\nwith   spaces.log"
    resp = client.post(
        "/api/uploads",
        files={"file": (weird, b"payload", "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    dest = Path(resp.json()["path"])
    # Control chars replaced, whitespace collapsed, extension intact.
    assert "\x00" not in dest.name
    assert "\n" not in dest.name
    assert "\t" not in dest.name
    assert "   " not in dest.name
    assert dest.suffix == ".log"
    # Grandparent is the configured upload root.
    assert dest.parent.parent == _uploads_dir(tmp_settings)


def test_upload_caps_absurdly_long_filename(client: TestClient, tmp_settings: Settings) -> None:
    """A 5000-character filename shouldn't blow past ext4's 255-byte
    basename limit. The sanitizer caps the stem at 200 chars and the
    extension is short, so the on-disk name stays well under the
    filesystem ceiling."""
    long_stem = "a" * 5000
    resp = client.post(
        "/api/uploads",
        files={"file": (f"{long_stem}.txt", b"ok", "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    dest = Path(resp.json()["path"])
    assert len(dest.name) <= 255
    assert dest.suffix == ".txt"
