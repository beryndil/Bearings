from __future__ import annotations

import pytest

from twrminal.agent.session import AgentSession


def test_agent_session_constructs() -> None:
    session = AgentSession(session_id="abc", working_dir="/tmp", model="claude-opus-4-7")
    assert session.session_id == "abc"
    assert session.model == "claude-opus-4-7"


@pytest.mark.asyncio
async def test_agent_session_stream_not_implemented() -> None:
    session = AgentSession(session_id="abc", working_dir="/tmp", model="claude-opus-4-7")
    with pytest.raises(NotImplementedError):
        async for _ in session.stream("hi"):
            break
