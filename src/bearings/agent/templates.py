"""Template lookup error for the agent layer.

Per ``docs/architecture-v1.md`` §1.1.4 the ``agent`` layer owns
domain-level glue between the DB storage layer
(:class:`bearings.db.templates.Template`) and the session-assembly API
surface.

:class:`TemplateNotFoundError` is raised by
:mod:`bearings.agent.session_assembly` when a template lookup fails;
keeping the exception here (rather than in the DB layer) preserves the
arch §3.1 layer boundary — the web layer imports from ``agent``, not
``db``, for error taxonomy.
"""

from __future__ import annotations


class TemplateNotFoundError(LookupError):
    """A template id did not match any row.

    Distinct from :class:`KeyError` so the API layer can distinguish a
    missing template (404) from any other lookup failure.
    """


__all__ = ["TemplateNotFoundError"]
