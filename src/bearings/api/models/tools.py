"""Tool-call and Todo DTOs. Mirrors the agent-side shapes so REST
first-paint and live WS events parse through the same schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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


class TodoItemOut(BaseModel):
    """One row in the live TodoWrite list. Mirrors
    `agent.events.TodoItem` on purpose — the first-paint REST shape
    and the live WS event carry the same per-item schema so the
    frontend reducer can treat them interchangeably.

    `active_form` uses `validation_alias="activeForm"` so the raw SDK
    input dict stored in `tool_calls.input_json` (camelCase) parses
    without renames, while the REST response ships snake_case to
    match every other Bearings wire shape and the frontend type."""

    content: str
    active_form: str | None = Field(default=None, validation_alias="activeForm")
    status: Literal["pending", "in_progress", "completed"]

    model_config = {"populate_by_name": True}


class TodosOut(BaseModel):
    """Reply shape for `GET /sessions/{id}/todos`. `todos` is `None`
    when the session has never invoked the TodoWrite tool, or an
    empty list when the agent explicitly cleared the list. This
    distinction lets the frontend render "no active todo session"
    vs. "todo session active but currently empty"."""

    todos: list[TodoItemOut] | None
