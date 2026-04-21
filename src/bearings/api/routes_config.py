"""UI-facing config surface.

Exposes only the settings the frontend needs to know at boot — currently
just the billing mode and (informational) plan slug — so the SvelteKit
bundle can pick a display strategy without reading the full config
file. Anything sensitive (auth tokens, absolute DB path) stays
server-side; this endpoint is deliberately a narrow allow-list.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from bearings.config import BillingMode

router = APIRouter(tags=["config"])


class UiConfigOut(BaseModel):
    """Minimal knob surface the frontend reads at startup.

    `billing_mode` drives the cost-vs-tokens display swap on session
    cards and the conversation header. `billing_plan` is informational
    only (currently just echoed back) so a future release can badge
    the header with the user's plan slug without a second endpoint."""

    billing_mode: BillingMode
    billing_plan: str | None = None


@router.get("/ui-config", response_model=UiConfigOut)
async def get_ui_config(request: Request) -> UiConfigOut:
    settings = request.app.state.settings
    return UiConfigOut(
        billing_mode=settings.billing.mode,
        billing_plan=settings.billing.plan,
    )
