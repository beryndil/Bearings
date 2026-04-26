"""Subscriber lifecycle helpers for `SessionRunner`.

Free functions covering subscribe / unsubscribe / reaper-eligibility.
State (`_subscribers`, `_event_log`, `_quiet_since`, `_status`) still
lives on the runner — these helpers manipulate it by reference without
owning it. Pulled out of `runner.py` to keep that file under the 400-
line cap and to group the reaper-clock bookkeeping (the `_quiet_since`
transitions in `unsubscribe`) next to the predicate that consumes it
(`should_reap`).

`event_fanout.py` continues to read `_subscribers` / `_event_log` /
`_next_seq` directly off the runner; that boundary is unchanged.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from bearings.agent.runner_types import SUBSCRIBER_QUEUE_MAX, _Envelope

if TYPE_CHECKING:
    from bearings.agent.runner import SessionRunner


async def subscribe(
    runner: SessionRunner, since_seq: int = 0
) -> tuple[asyncio.Queue[_Envelope], list[_Envelope]]:
    """Register a subscriber queue and return buffered events with
    seq > since_seq for replay. Reconnecting clients pass the last seq
    they saw; fresh clients pass 0 to replay the whole window.

    Queue is bounded by `SUBSCRIBER_QUEUE_MAX` — see
    `event_fanout._deliver` for the back-pressure / eviction policy."""
    queue: asyncio.Queue[_Envelope] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_MAX)
    runner._subscribers.add(queue)
    # A WS is attached — not quiet anymore. Clearing unconditionally is
    # simpler than checking prior state; the idle→running path also
    # clears it from the worker side.
    runner._quiet_since = None
    replay = [env for env in runner._event_log if env.seq > since_seq]
    return queue, replay


def unsubscribe(runner: SessionRunner, queue: asyncio.Queue[_Envelope]) -> None:
    """Drop a subscriber. If the last WS just walked away and no turn
    is in flight, start the reaper clock; if a turn is still running,
    wait for the worker's idle transition to start it — we don't want
    to evict a runner that's actively producing events even though its
    client left."""
    runner._subscribers.discard(queue)
    if runner._status == "idle" and not runner._subscribers:
        runner._quiet_since = time.monotonic()


def should_reap(runner: SessionRunner, now: float, ttl_seconds: float) -> bool:
    """Does this runner qualify for idle eviction?

    True iff it's currently quiet (idle, no subscribers) AND has been
    quiet for at least `ttl_seconds`. The registry reaper calls this
    under its lock; the runner itself does not act on eviction — that's
    the registry's job (pop + shutdown).
    """
    if runner._status != "idle":
        return False
    if runner._subscribers:
        return False
    if runner._quiet_since is None:
        return False
    return (now - runner._quiet_since) >= ttl_seconds
