from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from twrminal.agent.events import AgentEvent


@dataclass
class AgentSession:
    """Placeholder for the claude-agent-sdk-backed session.

    v0.1.0 scaffold only — real SDK wiring lands in the next commit.
    """

    session_id: str
    working_dir: str
    model: str

    async def stream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        raise NotImplementedError("AgentSession.stream is not wired — see TODO.md")
        yield  # pragma: no cover — keeps the type checker happy
