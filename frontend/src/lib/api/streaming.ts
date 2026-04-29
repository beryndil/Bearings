/**
 * WebSocket frame parser — mirrors
 * :func:`bearings.web.serialize.parse_frame` on the wire.
 *
 * Item 1.2 plumbs the WebSocket fan-out at
 * ``/ws/sessions/{session_id}`` and emits two frame shapes:
 *
 * - ``{"kind": "event", "seq": <int>, "event": <event-object>}`` —
 *   one :class:`bearings.agent.events.AgentEvent` per the spec §4.7
 *   discriminated union, plus a monotonic ``seq`` for ``since_seq``
 *   replay.
 * - ``{"kind": "heartbeat", "ts": <float>}`` — server liveness ping
 *   per ``docs/behavior/tool-output-streaming.md`` §"Long-tool keepalive".
 *
 * This module decodes those envelopes into discriminated TypeScript
 * unions so the conversation reducer can dispatch on ``frame.kind``
 * and ``frame.event.type`` without re-parsing JSON at the call site.
 */
import { WS_FRAME_KIND_EVENT, WS_FRAME_KIND_HEARTBEAT } from "../config";

import type { AgentEvent } from "./events";

export interface EventFrame {
  readonly kind: typeof WS_FRAME_KIND_EVENT;
  readonly seq: number;
  readonly event: AgentEvent;
}

export interface HeartbeatFrame {
  readonly kind: typeof WS_FRAME_KIND_HEARTBEAT;
  readonly ts: number;
}

export type StreamFrame = EventFrame | HeartbeatFrame;

/**
 * Parse a single text frame off the WebSocket. Returns ``null`` when
 * the frame is malformed; the conversation reducer treats ``null`` as
 * a no-op so a single bad frame doesn't tear down the stream.
 *
 * Pure-function shape — no side effects, suitable for unit testing
 * against synthetic JSON strings.
 */
export function parseStreamFrame(text: string): StreamFrame | null {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const obj = raw as Record<string, unknown>;
  const kind = obj.kind;
  if (kind === WS_FRAME_KIND_EVENT) {
    return parseEventFrame(obj);
  }
  if (kind === WS_FRAME_KIND_HEARTBEAT) {
    return parseHeartbeatFrame(obj);
  }
  return null;
}

function parseEventFrame(obj: Record<string, unknown>): EventFrame | null {
  const seq = obj.seq;
  if (typeof seq !== "number" || !Number.isInteger(seq) || seq < 0) {
    return null;
  }
  const event = obj.event;
  if (typeof event !== "object" || event === null) {
    return null;
  }
  const type = (event as Record<string, unknown>).type;
  if (typeof type !== "string") {
    return null;
  }
  // The Pydantic discriminated union on the backend already
  // guarantees the shape; we trust the wire and forward the typed
  // event. ``parseAgentEvent`` could be tightened later to validate
  // every field, but mirrors the JSON-Lines transport's
  // human-debuggable contract.
  return {
    kind: WS_FRAME_KIND_EVENT,
    seq,
    event: event as AgentEvent,
  };
}

function parseHeartbeatFrame(obj: Record<string, unknown>): HeartbeatFrame | null {
  const ts = obj.ts;
  if (typeof ts !== "number") {
    return null;
  }
  return { kind: WS_FRAME_KIND_HEARTBEAT, ts };
}
