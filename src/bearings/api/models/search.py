"""Search-result DTO served by the cross-session history endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class SearchHit(BaseModel):
    message_id: str
    session_id: str
    session_title: str | None = None
    model: str
    role: str
    snippet: str
    created_at: str
