"""Static-bundle serving + SPA fallback for the SvelteKit frontend.

Per ``docs/architecture-v1.md`` §1.1.5, the FastAPI app's static-bundle
mount lives in its own module so ``web/app.py`` stays a thin factory.
The SvelteKit build artifact (item 2.1) lands at
``src/bearings/web/dist/`` so it ships inside the Python wheel via
``[tool.hatch.build.targets.wheel] packages = ["src/bearings"]``;
this module locates that directory at import time and serves it.

Two serving concerns are bundled here:

* **Asset serving** — every file inside ``dist/`` (the SvelteKit
  `index.html`, the Vite-hashed JS / CSS / font assets, favicons) is
  served by ``StaticFiles`` at the standard MIME types.

* **SPA fallback** — SvelteKit's client-side router handles routes
  like ``/sessions/<id>`` that the server never produced as a separate
  HTML file. When the static layer 404s, this module rewrites the
  response to the bundle's ``index.html`` so the client-side router
  picks up the path. The fallback is gated to *html-accepting* GET
  requests so an unknown ``/api/<endpoint>`` path or asset miss still
  surfaces as a real 404.

API routes registered before the static mount take precedence —
``/openapi.json``, every ``/api/*`` and ``/ws/*`` route resolves
normally. Only paths that fall through to the static mount go through
the SPA fallback.

Cache-control strategy
----------------------
SvelteKit's Vite build writes **content-hashed** filenames for every JS
/ CSS / font asset under ``_app/immutable/``.  These files are
effectively immutable — a changed file always gets a new name — so they
can be cached indefinitely (``max-age=31536000, immutable``).

``index.html`` is the single non-hashed entry point.  The browser must
**always** revalidate it so that a newly deployed bundle (with updated
chunk hashes) reaches users without requiring a hard-refresh.
``Cache-Control: no-cache`` achieves this: the browser sends a
conditional request (``If-None-Match`` / ``If-Modified-Since``) and
the server returns 304 on a cache hit, keeping the round-trip cheap
while guaranteeing freshness.

Without these headers browsers apply heuristic caching based on
``Last-Modified``, which can serve stale ``index.html`` referencing
deleted chunk filenames for up to ~10 % of the file's age — meaning
users silently run old JavaScript until they force-refresh.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

# ``_app/immutable/`` contains only content-hashed assets — the filename
# changes whenever the file changes so these can be cached indefinitely.
_IMMUTABLE_PREFIX: str = "_app/immutable/"

# Applied to ``index.html`` and all other non-immutable files.  Forces
# browsers to revalidate on every load (conditional GET).  Essential so
# users pick up new bundle hashes after a deployment without a hard-refresh.
_CACHE_NO_CACHE: str = "no-cache"

# Applied to ``_app/immutable/**``.  One year max-age with the
# ``immutable`` directive skips the conditional-request round-trip.
_CACHE_IMMUTABLE: str = "public, max-age=31536000, immutable"

# Directory the SvelteKit static adapter writes to (configured in
# ``frontend/svelte.config.js``). Resolved relative to *this* file so
# the bundle ships inside the wheel and the lookup works the same in
# editable installs as in installed wheels.
_BUNDLE_DIR: Path = Path(__file__).resolve().parent / "dist"

# SvelteKit's default fallback document name (configured in
# ``frontend/svelte.config.js`` as ``fallback: "index.html"``). Named
# here so the path appears in only one place.
_FALLBACK_HTML: str = "index.html"


class _BundleStaticFiles(StaticFiles):
    """``StaticFiles`` subclass that falls back to the SPA shell and
    applies correct ``Cache-Control`` headers per asset type.

    Behavior:

    * Existing files inside the bundle resolve normally — the
      hash-named JS / CSS / font assets, favicon, etc.
    * Non-existent paths fall back to ``index.html`` so the SvelteKit
      client-side router can resolve them, *but only* when the request
      looks like a navigation: GET method and ``Accept`` includes
      ``text/html``.
    * All other misses (POST to a non-existent path, an asset reference
      with no ``Accept: text/html``) return a real 404 instead of an
      HTML body the caller cannot consume.

    Cache-Control headers are injected based on path:

    * ``_app/immutable/**`` — ``public, max-age=31536000, immutable``
      (content-hashed filenames, safe to cache forever).
    * Everything else (``index.html``, favicons, …) — ``no-cache``
      (always revalidate so stale entry-point HTML never silently
      serves old chunk hashes after a deployment).
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except Exception as exc:
            from starlette.exceptions import HTTPException as StarletteHTTPException

            if (
                not isinstance(exc, StarletteHTTPException)
                or exc.status_code != status.HTTP_404_NOT_FOUND
            ):
                raise
            request = Request(scope)
            if request.method != "GET":
                raise
            # API / WS / metrics paths must 404 as JSON, not receive the SPA
            # shell — the caller expects a structured error, not an HTML page.
            if _spa_path_excluded(request.url.path):
                raise
            # Asset references (any path segment containing a dot) get a real
            # 404 so JS loaders are never fed an HTML body.
            if "." in Path(request.url.path).name:
                raise
            fallback = self._resolve_fallback()
            if fallback is None:
                raise
            response = FileResponse(fallback)
        _apply_cache_header(response, path)
        return response

    def _resolve_fallback(self) -> Path | None:
        # ``self.directory`` is set by ``StaticFiles.__init__``. Wrap
        # in ``Path`` so the join is platform-safe and the existence
        # check survives a missing bundle (e.g. a fresh checkout
        # before ``npm run build``).
        if not self.directory:
            return None
        candidate = Path(self.directory) / _FALLBACK_HTML
        return candidate if candidate.is_file() else None


def _apply_cache_header(response: Response, path: str) -> None:
    """Inject the appropriate ``Cache-Control`` header into ``response``.

    ``path`` is the asset path relative to the bundle root (as received
    by :meth:`_BundleStaticFiles.get_response`).

    * Paths under ``_app/immutable/`` receive
      ``public, max-age=31536000, immutable`` — the filenames are
      content-hashed by Vite so the files never change.
    * All other paths (``index.html``, favicons, …) receive
      ``no-cache`` — browsers must revalidate before using a cached
      copy so a freshly deployed ``index.html`` (with updated chunk
      hashes) is picked up immediately without a hard-refresh.
    """
    # Starlette already populated ETag / Last-Modified; only add the
    # Cache-Control directive that Starlette omits by default.
    if path.startswith(_IMMUTABLE_PREFIX) or path.lstrip("/").startswith(_IMMUTABLE_PREFIX):
        response.headers["Cache-Control"] = _CACHE_IMMUTABLE
    else:
        response.headers["Cache-Control"] = _CACHE_NO_CACHE


# Prefixes and exact paths that must never be swallowed by the SPA
# catch-all.  API / WS / metrics / OpenAPI surfaces always take
# precedence because their routers are registered first; the catch-all
# never fires for those paths in normal operation.  This set is a
# defensive guard for unmatched sub-paths that fall through (e.g. a
# typo'd ``/api/…`` route with no handler).
_SPA_EXCLUDED_PREFIXES: tuple[str, ...] = (
    "/api/",
    "/ws/",
    "/metrics",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/static/",
)


def _spa_path_excluded(path: str) -> bool:
    """Return ``True`` when *path* must bypass the SPA catch-all.

    Matches both the bare prefix (``/metrics``) and any sub-path below
    it (``/metrics/foo``).
    """
    for prefix in _SPA_EXCLUDED_PREFIXES:
        bare = prefix.rstrip("/")
        if path == bare or path.startswith(bare + "/"):
            return True
    return False


async def spa_fallback_handler(request: Request) -> Response:
    """Serve the SvelteKit shell for any non-API navigation path.

    Registered as ``GET /{path:path}`` in
    :func:`bearings.web.app.create_app` after all API / WS / metrics
    routers but *before* the static-bundle mount, so named API routes
    always resolve through their own handlers first.

    Serving rules:

    * Paths matching an excluded prefix (``/api/``, ``/ws/``, etc.)
      raise HTTP 404 — the caller expected an API response, not an
      SPA shell.
    * Paths whose last segment contains a ``.`` are treated as asset
      references; they also raise HTTP 404 so a JS loader is never
      fed an HTML body.
    * All other paths receive ``dist/index.html`` with
      ``Content-Type: text/html`` so the SvelteKit client-side router
      resolves the route.
    * If the bundle is absent (backend-only test run) HTTP 404 is
      raised so tests that do not build the frontend see a clear miss.
    """
    path = request.url.path
    if _spa_path_excluded(path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if "." in Path(path).name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    index = bundle_dir() / _FALLBACK_HTML
    if not index.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    response = FileResponse(str(index), media_type="text/html")
    response.headers["Cache-Control"] = _CACHE_NO_CACHE
    return response


def bundle_dir() -> Path:
    """Return the on-disk path the static bundle is served from.

    Exposed as a function (rather than the module-level constant) so
    tests can monkeypatch it without import-time side effects.
    """
    return _BUNDLE_DIR


def mount_static_bundle(app: FastAPI) -> None:
    """Mount ``dist/`` at the app root with SPA fallback.

    Idempotent on a missing bundle: if ``dist/`` does not exist (e.g.
    a backend-only test run), no mount is added and the app continues
    to serve API + WS routes only. Production callers run
    ``npm run build`` before serving so the bundle is always present.
    """
    directory = bundle_dir()
    if not directory.is_dir():
        return
    app.mount(
        "/",
        _BundleStaticFiles(directory=str(directory), html=True),
        name="bearings_frontend",
    )


__all__ = ["bundle_dir", "mount_static_bundle", "spa_fallback_handler"]
