"""Pydantic request / response shapes for the ``bearings.web`` route modules.

Per ``docs/architecture-v1.md`` §1.1.5 each ``routes/<X>.py`` module
has a sibling ``models/<X>.py`` carrying its wire shapes. The package
is intentionally re-export-free — callers import the concern module
directly (``from bearings.web.models.tags import TagOut``).
"""

from __future__ import annotations

__all__: list[str] = []
