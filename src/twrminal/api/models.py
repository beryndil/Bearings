from __future__ import annotations

from pydantic import BaseModel


class SessionCreate(BaseModel):
    working_dir: str
    model: str
    title: str | None = None
    max_budget_usd: float | None = None


class SessionUpdate(BaseModel):
    """Partial update for an existing session. Any unset field is left
    unchanged; explicit `None` for `title`/`max_budget_usd` clears them."""

    title: str | None = None
    max_budget_usd: float | None = None
    # Distinguishes "not provided" from "set to null" for the two
    # nullable columns. Pydantic writes `model_fields_set` so routes
    # can dispatch off what was actually passed.


class SessionOut(BaseModel):
    id: str
    created_at: str
    updated_at: str
    working_dir: str
    model: str
    title: str | None = None
    max_budget_usd: float | None = None
    total_cost_usd: float = 0.0
    message_count: int = 0


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    thinking: str | None = None
    created_at: str


class ToolCallOut(BaseModel):
    id: str
    session_id: str
    message_id: str | None = None
    name: str
    input: str
    output: str | None = None
    error: str | None = None
    started_at: str
    finished_at: str | None = None


class SearchHit(BaseModel):
    message_id: str
    session_id: str
    session_title: str | None = None
    model: str
    role: str
    snippet: str
    created_at: str
