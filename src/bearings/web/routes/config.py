# mypy: disable-error-code=explicit-any
"""UI configuration endpoint.

``GET /api/ui-config`` surfaces the subset of runtime settings the frontend
needs to initialise its feature gates and billing display without a full DB
round-trip.

Response shape
--------------
::

    {
        "commands_scope": "project",  # scope for slash-command scanner
        "billing_mode": "payg",  # "payg" | "subscription"
        "feature_flags": {
            "reply_actions": true,
            "artifacts": true,
            "analytics": true,
            "spawn_from_reply": true,
        },
    }

All fields are derived from ``app.state`` (populated by ``create_app``).
The ``feature_flags`` map reflects which route groups are wired into the app;
in v1 all flags are ``True`` because every route group is always registered.

Exec-4 consumes this endpoint — keep the field names and types stable.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from bearings.config.constants import DEFAULT_BILLING_MODE

router = APIRouter()

# commands_scope: the slash-command scanner operates at project scope in v1
# (scanning only files under the session's working_dir rather than a global
# command registry).  This constant is the decided-and-documented default;
# future items may expose it as a Settings field.
_COMMANDS_SCOPE: str = "project"


class FeatureFlags(BaseModel):
    """Feature-gate map returned by GET /api/ui-config."""

    reply_actions: bool
    artifacts: bool
    analytics: bool
    spawn_from_reply: bool


class UiConfigOut(BaseModel):
    """Response body for GET /api/ui-config."""

    commands_scope: str
    billing_mode: str
    feature_flags: FeatureFlags


def _billing_mode(request: Request) -> str:
    """Read billing_mode from ``app.state``; fall back to the default."""
    raw = getattr(request.app.state, "billing_mode", None)
    if isinstance(raw, str) and raw:
        return raw
    return DEFAULT_BILLING_MODE


@router.get(
    "/api/ui-config",
    response_model=UiConfigOut,
    operation_id="get-ui-config",
    summary="Return frontend feature-gate configuration",
)
async def get_ui_config(request: Request) -> UiConfigOut:
    """Return the frontend configuration payload.

    In v1 all feature flags are always ``True``; future items may gate
    individual features behind Settings fields.
    """
    return UiConfigOut(
        commands_scope=_COMMANDS_SCOPE,
        billing_mode=_billing_mode(request),
        feature_flags=FeatureFlags(
            reply_actions=True,
            artifacts=True,
            analytics=True,
            spawn_from_reply=True,
        ),
    )


__all__ = ["router"]
