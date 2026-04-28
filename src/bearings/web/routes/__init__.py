"""FastAPI route modules for the Bearings v1 web surface.

Per ``docs/architecture-v1.md`` §1.1.5 every concern lives in its own
``routes/<X>.py`` module exposing a ``router`` :class:`fastapi.APIRouter`
for :func:`bearings.web.app.create_app` to mount. The package is
intentionally re-export-free — :mod:`bearings.web.app` imports each
``router`` by full path so a typo at the mount site fails type-check.
"""

from __future__ import annotations

__all__: list[str] = []
