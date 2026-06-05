"""Backward-compat re-export shim for ``bearings.web.routes.sessions``.

The session route implementation has been split across:

* ``sessions_core``      — list / create / get / delete / close / reopen
* ``sessions_model``     — model, permission_mode, pinned, full-PATCH
* ``sessions_prompts``   — prompt, stop, recover, regenerate, suggest-title
* ``sessions_assembly``  — viewed, paired-chat, tool_calls, todos, system_prompt, tokens
* ``sessions_io``        — export, import, work_evidence
* ``sessions_classify``  — spawn_classify (T2-07 sensitive-data classification)

This file assembles a single :data:`router` from those sub-routers so
``from bearings.web.routes.sessions import router`` continues to work
unchanged, and re-exports the private helpers that other modules import
directly (``sessions_bulk``, ``app.py``, ``tags.py``).
"""

from __future__ import annotations

from fastapi import APIRouter

from bearings.web.routes._sessions_helpers import (
    _sessions_broadcaster,
    _to_out,
)
from bearings.web.routes.sessions_assembly import router as _router_assembly
from bearings.web.routes.sessions_classify import router as _router_classify
from bearings.web.routes.sessions_core import router as _router_core
from bearings.web.routes.sessions_io import router as _router_io
from bearings.web.routes.sessions_model import router as _router_model
from bearings.web.routes.sessions_prompts import router as _router_prompts

# Assemble the combined router from all sub-routers.  APIRouter.include_router
# copies every route, so the combined router is functionally identical to the
# original monolithic router — same paths, same operation_ids.
router = APIRouter()
router.include_router(_router_core)
router.include_router(_router_model)
router.include_router(_router_prompts)
router.include_router(_router_assembly)
router.include_router(_router_io)
router.include_router(_router_classify)

# Re-export private helpers imported by other modules.
# sessions_bulk.py: from bearings.web.routes.sessions import _sessions_broadcaster, _to_out
# app.py:           from bearings.web.routes.sessions import _to_out
# tags.py:          from bearings.web.routes.sessions import _to_out
__all__ = [
    "_sessions_broadcaster",
    "_to_out",
    "router",
]
