"""Sunset response header middleware.

Per ``docs/deprecation-convention.md`` §3, routes carrying
``openapi_extra={"x-sunset": "<version>"}`` emit a ``Sunset`` response
header on every response per
`RFC 8594 <https://www.rfc-editor.org/rfc/rfc8594>`_.

The middleware inspects the matched route's metadata after FastAPI
routing completes. Routes without ``x-sunset`` (the majority) pass
through untouched.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Fixed sunset date for v1.2.0 deprecations. All deprecated surfaces
# currently targeted for removal in v1.2.0 share this date so clients
# see a single horizon.
_SUNSET_DATE_V1_2_0 = "Sat, 01 Jan 2027 00:00:00 GMT"


def _get_sunset_date(x_sunset_value: str) -> str | None:
    """Map the ``x-sunset`` version string to an HTTP-date for the header.

    Currently only ``v1.2.0`` is mapped; future deprecations will add
    entries here. Returns ``None`` for unknown versions (the header is
    not emitted for unmapped versions — defensive against typos).
    """
    mapping: dict[str, str] = {
        "v1.2.0": _SUNSET_DATE_V1_2_0,
    }
    return mapping.get(x_sunset_value)


class SunsetMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that emits ``Sunset`` headers for deprecated routes.

    Wraps each request/response cycle. After the response is generated,
    checks whether the matched route carries ``x-sunset`` in its
    ``openapi_extra``. If so, appends the ``Sunset`` header with the
    corresponding HTTP-date.

    Non-HTTP routes (WebSockets, etc.) pass through without inspection.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process the request and conditionally add the Sunset header."""
        response = await call_next(request)

        # Retrieve the matched route from the request scope. FastAPI sets
        # `scope["route"]` after routing; if absent (e.g., 404 or
        # non-HTTP transport), skip the header.
        route = request.scope.get("route")
        if route is None:
            return response

        # FastAPI/Starlette routes expose endpoint metadata via
        # `endpoint` or `app`. For APIRoute instances, the
        # `openapi_extra` lives on the route object if it was set in
        # the decorator.
        openapi_extra = getattr(route, "openapi_extra", None)
        if not isinstance(openapi_extra, dict):
            return response

        x_sunset = openapi_extra.get("x-sunset")
        if x_sunset is None:
            return response

        sunset_date = _get_sunset_date(str(x_sunset))
        if sunset_date is None:
            return response

        # Mutate response headers in-place. MutableHeaders is returned
        # by response.headers for Response subclasses.
        response.headers["Sunset"] = sunset_date
        return response


__all__ = ["SunsetMiddleware"]
