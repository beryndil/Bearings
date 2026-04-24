"""System-prompt layer snapshots served by the prompt inspection
endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class SystemPromptLayerOut(BaseModel):
    name: str
    kind: str
    content: str
    token_count: int


class SystemPromptOut(BaseModel):
    layers: list[SystemPromptLayerOut]
    total_tokens: int
