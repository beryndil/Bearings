# mypy: disable-error-code=explicit-any
"""Reply-actions routes — transformation catalog + apply.

Two endpoints:

* ``GET /api/reply_actions/catalog`` — returns the static list of available
  transformations (summarize, reformat, translate_plain, extract_key_points).
* ``POST /api/sessions/{session_id}/reply_actions`` — applies a transformation
  to a caller-supplied source message using the advisor and returns the
  transformed content.  Optionally records the result as a follow-up message
  on the session.  Returns 404 when the session does not exist.

The advisor call is isolated behind the module-level :data:`run_transform`
callable so tests can swap in a stub without spawning a real LLM call.

Exec-2B (work_evidence / spawn_classify) and Exec-4 (ui-config) build on
this surface — keep the catalog ids and the response shape stable.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Final

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from bearings.config.constants import REPLY_ACTION_ID_MAX_LENGTH
from bearings.db import messages as messages_db
from bearings.db import sessions as sessions_db
from bearings.web.routes._deps import _db

_LOG = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Transformation catalog — at least 3 entries per spec.
# ---------------------------------------------------------------------------

_CATALOG_ENTRIES: Final[list[dict[str, str]]] = [
    {
        "id": "summarize",
        "label": "Summarize",
        "description": ("Condense the message into a concise summary preserving the key points."),
        "instruction": (
            "Summarize the following message in a concise paragraph, "
            "preserving all key points and conclusions."
        ),
    },
    {
        "id": "reformat",
        "label": "Reformat",
        "description": ("Restructure the message for improved clarity and readability."),
        "instruction": (
            "Reformat the following message for clarity and structure. "
            "Use headings, bullet points, or numbered lists where appropriate."
        ),
    },
    {
        "id": "translate_plain",
        "label": "Simplify Language",
        "description": "Rewrite the message in plain, accessible language.",
        "instruction": (
            "Rewrite the following message in plain, simple language "
            "suitable for a general audience with no specialist background."
        ),
    },
    {
        "id": "extract_key_points",
        "label": "Extract Key Points",
        "description": "List the main actionable points from the message.",
        "instruction": (
            "Extract and list the key points and any actionable items "
            "from the following message as a numbered list."
        ),
    },
]

# ---------------------------------------------------------------------------
# Advisor callable — swap in tests via monkeypatch.
# ---------------------------------------------------------------------------

_RunTransformFn = Callable[[str, str], Awaitable[str]]


async def _stub_run_transform(content: str, instruction: str) -> str:  # pragma: no cover
    """Default stub — raises until a real implementation is injected.

    In production, callers should replace :data:`run_transform` with a
    function that calls the Claude API or the Bearings advisor.
    Tests always monkeypatch this before invoking the route.
    """
    del content, instruction  # unused in stub
    raise NotImplementedError(
        "reply_actions.run_transform has not been configured. "
        "Inject a real LLM callable at app startup or in tests."
    )


#: Module-level hook for the advisor call.  Replace with a real LLM callable
#: before serving, or monkeypatch in tests.  Signature:
#: ``async def fn(content: str, instruction: str) -> str``
run_transform: _RunTransformFn = _stub_run_transform

# ---------------------------------------------------------------------------
# Pydantic wire models
# ---------------------------------------------------------------------------


class ActionDescriptor(BaseModel):
    """One entry in the reply-actions catalog."""

    id: str
    label: str
    description: str
    instruction: str


class ApplyActionIn(BaseModel):
    """Request body for POST /api/sessions/{id}/reply_actions."""

    source_content: str = Field(
        min_length=1,
        description="The message text to transform.",
    )
    transformation_id: str = Field(
        min_length=1,
        max_length=REPLY_ACTION_ID_MAX_LENGTH,
        description="Catalog id of the transformation to apply.",
    )
    insert_follow_up: bool = Field(
        default=False,
        description=(
            "When True, insert the transformed content as a follow-up "
            "system message on the session."
        ),
    )


class ApplyActionOut(BaseModel):
    """Response body for POST /api/sessions/{id}/reply_actions."""

    content: str
    transformation_id: str
    inserted: bool


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.get(
    "/api/reply_actions/catalog",
    response_model=list[ActionDescriptor],
    operation_id="list-reply-action-catalog",
    summary="List available reply-action transformations",
)
async def get_reply_action_catalog() -> list[ActionDescriptor]:
    """Return the static catalog of available transformations."""
    return [ActionDescriptor(**entry) for entry in _CATALOG_ENTRIES]


@router.post(
    "/api/sessions/{session_id}/reply_actions",
    response_model=ApplyActionOut,
    status_code=status.HTTP_200_OK,
    operation_id="run-reply-action",
    summary="Apply a reply-action transformation to a message",
)
async def run_reply_action(
    session_id: str,
    body: ApplyActionIn,
    request: Request,
) -> ApplyActionOut:
    """Apply *transformation_id* to *source_content*.

    Returns 404 when the session does not exist.
    Returns 422 when *transformation_id* is not in the catalog.
    Returns 501 when the advisor callable has not been configured.
    Returns 502 when the advisor call fails.
    """
    db = _db(request)
    session = await sessions_db.get(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session {session_id!r} not found",
        )

    # Validate transformation_id against catalog.
    catalog_ids = {entry["id"] for entry in _CATALOG_ENTRIES}
    if body.transformation_id not in catalog_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"transformation_id {body.transformation_id!r} not in catalog; "
                f"valid ids: {sorted(catalog_ids)}"
            ),
        )

    instruction = next(
        entry["instruction"] for entry in _CATALOG_ENTRIES if entry["id"] == body.transformation_id
    )

    try:
        result = await run_transform(body.source_content, instruction)
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        _LOG.warning("apply_reply_action: advisor call failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Advisor call failed: {exc}",
        ) from exc

    # Optional follow-up insertion: insert the transformed content as a
    # system-role message on the session so it appears in the transcript.
    # The WS event stream for connected clients refreshes on next
    # reconnect; this is acceptable for an explicit user-triggered action.
    inserted = False
    if body.insert_follow_up:
        try:
            await messages_db.insert_system(db, session_id=session_id, content=result)
            inserted = True
        except Exception as exc:
            _LOG.warning(
                "reply_action insert_follow_up failed session=%s: %s",
                session_id,
                exc,
            )

    return ApplyActionOut(
        content=result,
        transformation_id=body.transformation_id,
        inserted=inserted,
    )


__all__ = ["router", "run_transform"]
