"""Cache-control headers on the SvelteKit bundle mount.

Why this matters: `index.html` is the entry point that references the
*current* build's hashed chunks under `_app/immutable/`. Without an
explicit Cache-Control header, browsers heuristically cache it; on the
next deploy the chunks are at new hashes but the cached `index.html`
still points at the old ones, so the user runs old code until they
Ctrl+Shift+R. The mount in `server.py` is wrapped in `_BundleStaticFiles`
specifically to break that — these tests pin the contract so a future
refactor can't silently regress it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def static_app(tmp_path: Path):
    """A bare app with the bundle mount pointed at a temp dir, so the
    test owns the file layout and doesn't depend on whether the SvelteKit
    bundle has been built. Isolated from the full app fixture in
    `conftest.py` because we don't want lifespan / DB / runner setup
    just to assert HTTP headers."""
    from fastapi import FastAPI

    from bearings.server import _BundleStaticFiles

    # Mock a SvelteKit-shaped output: an entry index.html, a hashed
    # immutable chunk, and a non-hashed sibling (manifest.webmanifest)
    # to exercise both branches of the Cache-Control split.
    (tmp_path / "_app" / "immutable" / "nodes").mkdir(parents=True)
    (tmp_path / "_app" / "immutable" / "nodes" / "0.abcdef.js").write_text("console.log('hashed');")
    (tmp_path / "index.html").write_text("<html><body>fake bundle</body></html>")
    (tmp_path / "manifest.webmanifest").write_text('{"name":"test"}')

    app = FastAPI()
    app.mount("/", _BundleStaticFiles(directory=tmp_path, html=True), name="frontend")
    return TestClient(app)


def test_immutable_chunk_caches_forever(static_app: TestClient) -> None:
    """Hashed bundle chunks are content-addressed: the filename
    changes whenever the bytes change, so a cached entry can never be
    stale. Tell the browser to skip revalidation entirely."""
    resp = static_app.get("/_app/immutable/nodes/0.abcdef.js")
    assert resp.status_code == 200
    cache = resp.headers.get("cache-control", "")
    assert "max-age=31536000" in cache
    assert "immutable" in cache


def test_index_html_must_revalidate(static_app: TestClient) -> None:
    """`index.html` is the entry point and must reach the user fresh
    after every rebuild. `no-cache` (which actually means "always
    revalidate") combined with the StaticFiles ETag yields cheap 304s
    when bytes are unchanged and immediate 200s when they're not."""
    resp = static_app.get("/")
    assert resp.status_code == 200
    cache = resp.headers.get("cache-control", "")
    assert "no-cache" in cache


def test_non_hashed_sibling_must_revalidate(static_app: TestClient) -> None:
    """Anything else at the bundle root (manifest, favicon) follows
    the same revalidate-always rule as `index.html` — these files are
    NOT hashed, so they suffer the same staleness problem if cached
    indefinitely."""
    resp = static_app.get("/manifest.webmanifest")
    assert resp.status_code == 200
    cache = resp.headers.get("cache-control", "")
    assert "no-cache" in cache
