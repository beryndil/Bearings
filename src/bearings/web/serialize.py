# mypy: disable-error-code=explicit-any
"""Wire-frame serialization for the streaming WebSocket protocol.

Item 1.2 — translates :class:`bearings.agent.events.AgentEvent` to a
JSON-Lines wire frame and back. The two functions :func:`event_frame`
and :func:`heartbeat_frame` produce the two frame ``kind`` values the
client observes; :func:`parse_frame` round-trips both.

The ``mypy: disable-error-code=explicit-any`` pragma is the same
narrow carve-out :mod:`bearings.agent.events` and
:mod:`bearings.config.settings` make for Pydantic's metaclass-exposed
``Any`` surface (the :class:`pydantic.TypeAdapter` factory's generic
parameter resolves to ``Any`` in mypy's view of the SDK type's
machinery). Restricting the disable to this file keeps the carve-out
narrow — every public function below has a fully-typed signature.

Frame format — JSON object per WebSocket text message. Two ``kind``
shapes:

* ``{"kind": "event", "seq": <int>, "event": <event-object>}``
  carries one :class:`AgentEvent`. ``seq`` is the runner's monotonic
  sequence number (item 1.2 — :class:`bearings.agent.runner.SessionRunner`'s
  ring buffer assigns it). The event-object's nested ``type`` field
  is the :class:`AgentEvent` discriminator
  (per arch §4.7 / events.py).
* ``{"kind": "heartbeat", "ts": <float>}``
  the server liveness ping per
  ``docs/behavior/tool-output-streaming.md`` §"Long-tool keepalive"
  + arch §1.1.2 ``WS_IDLE_PING_INTERVAL_S``. ``ts`` is unix seconds
  (server clock); the client uses it only to verify the connection
  isn't stalled.

Why JSON-Lines + envelope (vs single-frame-per-event without
envelope, vs MessagePack, vs protobuf):

* Behavior doc §"Reconnect / replay" requires a sequence number for
  ``since_seq`` resume. Inlining ``seq`` into every event would
  pollute the :class:`AgentEvent` Pydantic schema with a transport
  concern; the envelope keeps it clean.
* JSON-Lines is what the SvelteKit frontend (item 2.x) reads
  natively via ``WebSocket.onmessage`` → ``JSON.parse``. MessagePack
  would force a frontend codec round-trip with no tangible payoff
  for a localhost transport.
* The frontend / wire shape stays human-debuggable. ``curl --raw``
  + ``websocat`` users see real text frames.

References:

* ``docs/architecture-v1.md`` §4.7 — :class:`AgentEvent` discriminated
  union + Pydantic shape.
* ``docs/behavior/tool-output-streaming.md`` — "Reconnect / replay",
  "Long-tool keepalive".
* ``docs/architecture-v1.md`` §1.1.2 / §1.1.5 — ``RING_BUFFER_MAX`` /
  ``WS_IDLE_PING_INTERVAL_S`` constants and the web-layer host.
"""

from __future__ import annotations

import json
import time
from typing import Final, Literal, TypedDict

from pydantic import TypeAdapter, ValidationError

from bearings.agent.events import AgentEvent

# ``TypeAdapter`` over the discriminated union resolves the right
# variant from the ``type`` field at parse time. Module-level instance
# so the schema is constructed once per process — Pydantic reuses the
# compiled schema on every ``validate_*`` / ``dump_*`` call.
_EVENT_ADAPTER: Final[TypeAdapter[AgentEvent]] = TypeAdapter(AgentEvent)

# Frame ``kind`` values — single source of truth so a typo at the
# call site (here or in the consumer) fails type-check.
FRAME_KIND_EVENT: Final[str] = "event"
FRAME_KIND_HEARTBEAT: Final[str] = "heartbeat"


class _EventFrameDict(TypedDict):
    kind: Literal["event"]
    seq: int
    event: dict[str, object]


class _HeartbeatFrameDict(TypedDict):
    kind: Literal["heartbeat"]
    ts: float


def event_frame(seq: int, event: AgentEvent) -> str:
    """Serialise ``(seq, event)`` to a JSON-Lines wire frame.

    Round-trip: :func:`parse_frame` deserialises the result back to
    ``("event", seq, event)``. Pydantic's ``model_dump`` is the source
    of the event-object's JSON shape; the envelope wraps it.
    """
    if seq < 0:
        raise ValueError(f"seq must be >= 0 (got {seq})")
    payload: _EventFrameDict = {
        "kind": "event",
        "seq": seq,
        "event": event.model_dump(mode="json"),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def heartbeat_frame(ts: float | None = None) -> str:
    """Serialise a heartbeat frame at ``ts`` (defaults to ``time.time()``)."""
    payload: _HeartbeatFrameDict = {
        "kind": "heartbeat",
        "ts": time.time() if ts is None else ts,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parse_frame(
    text: str,
) -> tuple[Literal["event"], int, AgentEvent] | tuple[Literal["heartbeat"], float]:
    """Round-trip parse of an event or heartbeat frame.

    Returns a tagged tuple — ``("event", seq, event)`` or
    ``("heartbeat", ts)``. Raises :class:`ValueError` on malformed
    input (missing ``kind``, unknown ``kind``, malformed envelope) and
    :class:`pydantic.ValidationError` on event-object shape failures
    (so test assertions can distinguish "wrong wire shape" from "wrong
    event shape").
    """
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"frame is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"frame must be a JSON object, got {type(raw).__name__}")
    kind = raw.get("kind")
    if kind == FRAME_KIND_EVENT:
        return _parse_event_frame(raw)
    if kind == FRAME_KIND_HEARTBEAT:
        return _parse_heartbeat_frame(raw)
    raise ValueError(
        f"unknown frame kind {kind!r}; expected {FRAME_KIND_EVENT!r} or {FRAME_KIND_HEARTBEAT!r}"
    )


def _parse_event_frame(raw: dict[str, object]) -> tuple[Literal["event"], int, AgentEvent]:
    seq = raw.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool):
        raise ValueError(f"event frame 'seq' must be int, got {type(seq).__name__}")
    if seq < 0:
        raise ValueError(f"event frame 'seq' must be >= 0 (got {seq})")
    event_payload = raw.get("event")
    if not isinstance(event_payload, dict):
        raise ValueError(
            f"event frame 'event' must be a JSON object, got {type(event_payload).__name__}"
        )
    try:
        event = _EVENT_ADAPTER.validate_python(event_payload)
    except ValidationError:
        raise
    return ("event", seq, event)


def _parse_heartbeat_frame(raw: dict[str, object]) -> tuple[Literal["heartbeat"], float]:
    ts = raw.get("ts")
    # JSON numbers parse as int or float; both are acceptable.
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        raise ValueError(f"heartbeat frame 'ts' must be number, got {type(ts).__name__}")
    return ("heartbeat", float(ts))


__all__ = [
    "FRAME_KIND_EVENT",
    "FRAME_KIND_HEARTBEAT",
    "event_frame",
    "heartbeat_frame",
    "parse_frame",
]
