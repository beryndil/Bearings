"""Integration tests for ``bearings.web.static`` (item 2.1).

Locks the SvelteKit bundle's serving contract:

* ``GET /`` returns the bundle's ``index.html`` with ``text/html``.
* SPA fallback — a path the server never produced (``/sessions/foo``)
  with ``Accept: text/html`` falls back to ``index.html`` so the
  client-side router resolves it.
* ``/openapi.json`` and ``/api/health`` still respond normally; the
  static mount does not shadow API surfaces (mount-order regression
  guard).
* On a missing bundle (the ``dist/`` directory absent), the app
  factory does not raise and API surfaces continue to work; this is
  the contract for backend-only test runs.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bearings.web import static as static_mod
from bearings.web.app import create_app

_BUNDLE_DIR: Path = Path(__file__).resolve().parents[1] / "src" / "bearings" / "web" / "dist"
_INDEX_HTML: Path = _BUNDLE_DIR / "index.html"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Construct the app with the real on-disk bundle."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.skipif(
    not _INDEX_HTML.is_file(),
    reason="bundle not built — run `npm run build` in frontend/ first",
)
def test_root_returns_bundle_index_html(client: TestClient) -> None:
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    # The bundle ships our app shell — the title tag survives the
    # SvelteKit prerender so a substring assertion is enough.
    assert "<title>Bearings</title>" in response.text


@pytest.mark.skipif(
    not _INDEX_HTML.is_file(),
    reason="bundle not built — run `npm run build` in frontend/ first",
)
def test_spa_fallback_serves_index_for_unknown_navigation(client: TestClient) -> None:
    response = client.get("/sessions/nonexistent", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Bearings</title>" in response.text


@pytest.mark.skipif(
    not _INDEX_HTML.is_file(),
    reason="bundle not built — run `npm run build` in frontend/ first",
)
def test_unknown_non_html_request_returns_404(client: TestClient) -> None:
    # An asset reference (no Accept: text/html) should NOT fall back to
    # index.html — that would feed a JS loader an HTML body.
    response = client.get(
        "/_app/immutable/does-not-exist.js",
        headers={"Accept": "application/javascript"},
    )
    assert response.status_code == 404


@pytest.mark.skipif(
    not _INDEX_HTML.is_file(),
    reason="bundle not built — run `npm run build` in frontend/ first",
)
def test_openapi_endpoint_is_not_shadowed(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["info"]["title"] == "Bearings"


@pytest.mark.skipif(
    not _INDEX_HTML.is_file(),
    reason="bundle not built — run `npm run build` in frontend/ first",
)
def test_health_endpoint_is_not_shadowed(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.skipif(
    not _INDEX_HTML.is_file(),
    reason="bundle not built — run `npm run build` in frontend/ first",
)
def test_spa_catch_all_serves_html_for_deep_link(client: TestClient) -> None:
    """BUG-NET-23: direct navigation to SPA routes returns the SvelteKit shell.

    Verifies that paths like ``/tags``, ``/vault``, ``/settings`` etc.
    return HTTP 200 + ``text/html`` with the hydration marker instead
    of the FastAPI JSON 404 that fired when no API route matched.
    """
    spa_paths = [
        "/tags",
        "/memories",
        "/vault",
        "/analytics",
        "/settings",
        "/sessions/new",
    ]
    for path in spa_paths:
        response = client.get(path)
        assert response.status_code == 200, f"Expected 200 for {path}, got {response.status_code}"
        assert response.headers["content-type"].startswith("text/html"), (
            f"Expected text/html for {path}"
        )
        assert "<title>Bearings</title>" in response.text, (
            f"SvelteKit hydration marker missing for {path}"
        )


def test_api_404_not_shadowed_by_spa_catch_all() -> None:
    """BUG-NET-23: unknown ``/api/*`` paths still return JSON 404, not the SPA shell.

    The catch-all's excluded-prefix guard must prevent the SvelteKit
    shell from being served in place of a genuine API 404 response.
    Runs without a built bundle — the path exclusion fires before any
    filesystem check.
    """
    app = create_app()
    with TestClient(app) as tc:
        response = tc.get("/api/nonsense")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Not Found"}


def test_factory_tolerates_missing_bundle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Backend-only test runs can construct the app even with no dist/."""
    nonexistent = tmp_path / "no-bundle-here"
    monkeypatch.setattr(static_mod, "bundle_dir", lambda: nonexistent)

    app = create_app()
    with TestClient(app) as test_client:
        # API surface still works.
        response = test_client.get("/openapi.json")
        assert response.status_code == 200
        # Without the bundle mounted, root request 404s — and that 404
        # comes from FastAPI, not our SPA fallback.
        root = test_client.get("/", headers={"Accept": "text/html"})
        assert root.status_code == 404


# ---------------------------------------------------------------------------
# Cache-Control header tests (BUG: missing headers caused heuristic caching
# of index.html, serving stale JS to users and breaking real-time rendering
# until a hard-refresh).
# ---------------------------------------------------------------------------


def test_apply_cache_header_no_cache_for_index() -> None:
    """Non-immutable paths (index.html) receive Cache-Control: no-cache."""
    from starlette.responses import Response

    from bearings.web.static import _apply_cache_header

    resp = Response(content="", status_code=200)
    _apply_cache_header(resp, "index.html")
    assert resp.headers["Cache-Control"] == "no-cache"


def test_apply_cache_header_immutable_for_hashed_asset() -> None:
    """Content-hashed assets receive long-lived Cache-Control: immutable."""
    from starlette.responses import Response

    from bearings.web.static import _apply_cache_header

    resp = Response(content="", status_code=200)
    _apply_cache_header(resp, "_app/immutable/entry/app.DQ8YJbEi.js")
    assert resp.headers["Cache-Control"] == "public, max-age=31536000, immutable"


def test_apply_cache_header_no_cache_for_favicon() -> None:
    """favicon.png and other non-hashed assets also receive no-cache."""
    from starlette.responses import Response

    from bearings.web.static import _apply_cache_header

    resp = Response(content="", status_code=200)
    _apply_cache_header(resp, "favicon.png")
    assert resp.headers["Cache-Control"] == "no-cache"


@pytest.mark.skipif(
    not _INDEX_HTML.is_file(),
    reason="bundle not built — run `npm run build` in frontend/ first",
)
def test_index_html_cache_control_no_cache(client: TestClient) -> None:
    """GET / must return Cache-Control: no-cache so browsers always revalidate.

    Without this header browsers apply heuristic caching (≈ Last-Modified
    age / 10) and serve a stale index.html after deployments, which
    causes the old JS bundle (referencing deleted chunk filenames) to run
    silently until the user force-refreshes.
    """
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.headers.get("Cache-Control") == "no-cache"


@pytest.mark.skipif(
    not _INDEX_HTML.is_file(),
    reason="bundle not built — run `npm run build` in frontend/ first",
)
def test_immutable_chunk_cache_control(client: TestClient) -> None:
    """Content-hashed JS chunk must carry the long-lived immutable directive."""
    # Pick the first .js file under _app/immutable/entry/ that exists on disk.
    entry_dir = _BUNDLE_DIR / "_app" / "immutable" / "entry"
    js_files = list(entry_dir.glob("*.js")) if entry_dir.is_dir() else []
    if not js_files:
        pytest.skip("no entry JS chunks found in bundle")
    js_path = f"/_app/immutable/entry/{js_files[0].name}"
    response = client.get(js_path)
    assert response.status_code == 200
    cc = response.headers.get("Cache-Control", "")
    assert "immutable" in cc, f"Expected immutable in Cache-Control, got: {cc!r}"
    assert "max-age=31536000" in cc


@pytest.mark.skipif(
    not _INDEX_HTML.is_file(),
    reason="bundle not built — run `npm run build` in frontend/ first",
)
def test_spa_fallback_cache_control_no_cache(client: TestClient) -> None:
    """SPA fallback (deep-link to unknown path) also gets Cache-Control: no-cache."""
    response = client.get("/sessions/some-id", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.headers.get("Cache-Control") == "no-cache"
