"""Lifecycle state-machine tests for :class:`bearings.agent.session.AgentSession`.

Verifies the transition table from :mod:`bearings.agent.session`
matches arch §1.1.4 + ``docs/behavior/chat.md`` §"The agent loop
start/stop semantics" + §"Error states":

* every named happy-path edge succeeds;
* every edge NOT in :data:`LIFECYCLE_TRANSITIONS` raises
  :class:`SessionStateError` (the autonomy contract's "transitions
  valid only from named source states");
* concurrent transitions from two coroutines serialise on the
  internal ``asyncio.Lock`` so two callers cannot race ``pause`` /
  ``close`` on the same session;
* ``CLOSED`` is terminal — every transition out raises.
"""

from __future__ import annotations

import asyncio

import pytest

from bearings.agent.routing import RoutingDecision
from bearings.agent.session import (
    LIFECYCLE_TRANSITIONS,
    AgentSession,
    SessionConfig,
    SessionState,
    SessionStateError,
)


def _make_decision() -> RoutingDecision:
    return RoutingDecision(
        executor_model="sonnet",
        advisor_model="opus",
        advisor_max_uses=5,
        effort_level="auto",
        source="default",
        reason="lifecycle test default",
        matched_rule_id=None,
    )


def _make_session() -> AgentSession:
    config = SessionConfig(
        session_id="sess-1",
        working_dir="/tmp/lifecycle",
        decision=_make_decision(),
        db=None,
    )
    return AgentSession(config)


# ---------------------------------------------------------------------------
# Transition table — happy paths
# ---------------------------------------------------------------------------


async def test_initial_state_is_initializing() -> None:
    sess = _make_session()
    assert sess.state == SessionState.INITIALIZING
    assert sess.error_message is None
    assert sess.has_sdk_client is False


async def test_start_transitions_to_running() -> None:
    sess = _make_session()
    await sess.start()
    assert sess.state == SessionState.RUNNING


async def test_pause_then_resume_cycles() -> None:
    sess = _make_session()
    await sess.start()
    await sess.pause()
    # Read state into a local before/after each transition so mypy
    # doesn't flow-narrow the property to the asserted constant and
    # then complain that the next transition's expected state is
    # unreachable.
    after_pause = sess.state
    assert after_pause == SessionState.PAUSED
    await sess.resume()
    after_resume = sess.state
    assert after_resume == SessionState.RUNNING


async def test_close_from_running_terminates() -> None:
    sess = _make_session()
    await sess.start()
    await sess.close()
    assert sess.state == SessionState.CLOSED


async def test_close_from_paused_terminates() -> None:
    sess = _make_session()
    await sess.start()
    await sess.pause()
    await sess.close()
    assert sess.state == SessionState.CLOSED


async def test_close_from_initializing_terminates() -> None:
    """Per LIFECYCLE_TRANSITIONS, ``INITIALIZING → CLOSED`` is allowed
    (the user cancels a session before the runner starts)."""
    sess = _make_session()
    await sess.close()
    assert sess.state == SessionState.CLOSED


async def test_mark_error_records_message() -> None:
    sess = _make_session()
    await sess.start()
    await sess.mark_error("API rate limited")
    assert sess.state == SessionState.ERROR
    assert sess.error_message == "API rate limited"


async def test_recover_clears_error() -> None:
    sess = _make_session()
    await sess.start()
    await sess.mark_error("transient")
    await sess.recover()
    assert sess.state == SessionState.RUNNING
    assert sess.error_message is None


async def test_close_from_error_terminates() -> None:
    sess = _make_session()
    await sess.start()
    await sess.mark_error("fatal")
    await sess.close()
    assert sess.state == SessionState.CLOSED


async def test_error_from_initializing_is_allowed() -> None:
    """A failed-to-start session can land directly in ERROR."""
    sess = _make_session()
    await sess.mark_error("startup failed")
    assert sess.state == SessionState.ERROR


async def test_error_from_paused_is_allowed() -> None:
    sess = _make_session()
    await sess.start()
    await sess.pause()
    await sess.mark_error("error while paused")
    assert sess.state == SessionState.ERROR


# ---------------------------------------------------------------------------
# Transition table — invalid edges
# ---------------------------------------------------------------------------


async def test_pause_from_initializing_raises() -> None:
    sess = _make_session()
    with pytest.raises(SessionStateError):
        await sess.pause()


async def test_resume_from_running_raises() -> None:
    """``resume`` only valid out of PAUSED or ERROR; not from RUNNING."""
    sess = _make_session()
    await sess.start()
    with pytest.raises(SessionStateError):
        await sess.resume()


async def test_resume_from_initializing_raises() -> None:
    sess = _make_session()
    with pytest.raises(SessionStateError):
        await sess.resume()


async def test_start_from_running_raises() -> None:
    """``start`` is only valid from INITIALIZING."""
    sess = _make_session()
    await sess.start()
    with pytest.raises(SessionStateError):
        await sess.start()


async def test_pause_from_paused_raises() -> None:
    sess = _make_session()
    await sess.start()
    await sess.pause()
    with pytest.raises(SessionStateError):
        await sess.pause()


async def test_pause_from_closed_raises() -> None:
    sess = _make_session()
    await sess.close()
    with pytest.raises(SessionStateError):
        await sess.pause()


async def test_resume_from_closed_raises() -> None:
    sess = _make_session()
    await sess.close()
    with pytest.raises(SessionStateError):
        await sess.resume()


async def test_mark_error_from_closed_raises() -> None:
    """CLOSED is terminal — even error reports are rejected."""
    sess = _make_session()
    await sess.close()
    with pytest.raises(SessionStateError):
        await sess.mark_error("oops")


async def test_close_from_closed_raises() -> None:
    """No double-close — also tests CLOSED has empty allowed-set."""
    sess = _make_session()
    await sess.close()
    with pytest.raises(SessionStateError):
        await sess.close()


async def test_error_from_error_raises() -> None:
    """``mark_error`` cannot stack errors; must recover or close first."""
    sess = _make_session()
    await sess.start()
    await sess.mark_error("first")
    with pytest.raises(SessionStateError):
        await sess.mark_error("second")


# ---------------------------------------------------------------------------
# Transition table self-consistency
# ---------------------------------------------------------------------------


def test_transitions_table_covers_every_state() -> None:
    """Every :class:`SessionState` value has an entry in the table."""
    assert set(LIFECYCLE_TRANSITIONS) == set(SessionState)


def test_closed_is_terminal() -> None:
    """``CLOSED`` has zero outgoing edges."""
    assert LIFECYCLE_TRANSITIONS[SessionState.CLOSED] == frozenset()


def test_every_target_is_a_session_state() -> None:
    """No table value contains a non-SessionState (e.g. typo'd literal)."""
    for source, targets in LIFECYCLE_TRANSITIONS.items():
        for target in targets:
            assert isinstance(target, SessionState), (
                f"source={source!r} has non-state target {target!r}"
            )


# ---------------------------------------------------------------------------
# Concurrent-transition guard
# ---------------------------------------------------------------------------


async def test_concurrent_close_serialises_via_lock() -> None:
    """Two concurrent ``close()`` calls — exactly one succeeds, the
    other observes the terminal CLOSED and raises.

    The lock guarantees the transition guard sees a coherent state;
    without it, both calls could read ``RUNNING``, race past the
    guard, and both flip the state — only the second would notice the
    invariant break, but only because the table check is then run
    against a stale snapshot.
    """
    sess = _make_session()
    await sess.start()

    results = await asyncio.gather(
        sess.close(),
        sess.close(),
        return_exceptions=True,
    )
    # Exactly one is None (success), exactly one is SessionStateError.
    successes = [r for r in results if r is None]
    failures = [r for r in results if isinstance(r, SessionStateError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert sess.state == SessionState.CLOSED


async def test_concurrent_pause_and_close_serialise() -> None:
    """``pause`` and ``close`` racing — both are valid from RUNNING,
    so whichever wins lands first; the loser sees the new state and
    either succeeds (if still allowed) or fails."""
    sess = _make_session()
    await sess.start()

    pause_result, close_result = await asyncio.gather(
        sess.pause(),
        sess.close(),
        return_exceptions=True,
    )
    # One of two outcomes is acceptable:
    #  - pause won: state went RUNNING → PAUSED → CLOSED (close legal
    #    from PAUSED), both succeed, final state = CLOSED.
    #  - close won: state went RUNNING → CLOSED, then pause from
    #    CLOSED raised, final state = CLOSED.
    assert sess.state == SessionState.CLOSED
    if isinstance(pause_result, BaseException):
        assert isinstance(pause_result, SessionStateError)
    if isinstance(close_result, BaseException):
        assert isinstance(close_result, SessionStateError)
