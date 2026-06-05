"""Backward-compat re-export shim for ``bearings.db.sessions``.

The sessions DB layer has been split across:

* ``_sessions_base``    — Session dataclass, validators, filter SQL helpers
* ``sessions_read``     — get, exists, list_all, list_paged + SQL infrastructure
* ``sessions_write``    — create, import_session, delete, close, reopen, lifecycle
* ``sessions_update``   — update_fields, update_*, close_with_summary
* ``sessions_messages`` — is_closed, get_kind, get_paired_chat_info, get_by_pivot_message_id

This file re-exports every public symbol so that
``from bearings.db.sessions import Session`` and
``from bearings.db import sessions as sessions_db; sessions_db.get(...)``
continue to work unchanged throughout the codebase.
"""

from __future__ import annotations

from bearings.db._sessions_base import Session
from bearings.db.sessions_messages import (
    get_by_pivot_message_id,
    get_kind,
    get_paired_chat_info,
    is_closed,
)
from bearings.db.sessions_read import (
    exists,
    get,
    list_all,
    list_paged,
)
from bearings.db.sessions_update import (
    close_with_summary,
    set_classified,
    update_fields,
    update_model,
    update_permission_mode,
    update_routing_decision,
    update_title,
)
from bearings.db.sessions_write import (
    add_to_total_cost,
    close,
    create,
    delete,
    import_session,
    mark_viewed,
    reopen,
    set_error_pending,
    update_pinned,
)

__all__ = [
    "Session",
    "add_to_total_cost",
    "close",
    "close_with_summary",
    "create",
    "delete",
    "exists",
    "get",
    "get_by_pivot_message_id",
    "get_kind",
    "get_paired_chat_info",
    "import_session",
    "is_closed",
    "list_all",
    "list_paged",
    "mark_viewed",
    "reopen",
    "set_classified",
    "set_error_pending",
    "update_fields",
    "update_model",
    "update_permission_mode",
    "update_pinned",
    "update_routing_decision",
    "update_title",
]
