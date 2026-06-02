"""Bearings ASGI middleware.

Per ``docs/architecture-v1.md`` §1.1.5 ``web/middleware/`` contains
ASGI middleware classes wired into ``create_app()``.
"""

from bearings.web.middleware.sunset import SunsetMiddleware

__all__ = ["SunsetMiddleware"]
