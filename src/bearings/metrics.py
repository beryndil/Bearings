"""Prometheus collectors for Bearings.

One shared ``CollectorRegistry`` so `/metrics` emits only the metrics we
own (not the default Python process collectors). All instrumentation
lives at the route / WS-handler boundary — the store and agent layers
stay side-effect-free.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge

REGISTRY = CollectorRegistry()

sessions_created = Counter(
    "bearings_sessions_created_total",
    "Number of sessions created via POST /api/sessions.",
    registry=REGISTRY,
)

messages_persisted = Counter(
    "bearings_messages_persisted_total",
    "Number of messages written to the database, by role.",
    ["role"],
    registry=REGISTRY,
)

tool_calls_started = Counter(
    "bearings_tool_calls_started_total",
    "Number of tool calls begun (ToolCallStart events).",
    registry=REGISTRY,
)

tool_calls_finished = Counter(
    "bearings_tool_calls_finished_total",
    "Number of tool calls completed, labeled by success.",
    ["ok"],
    registry=REGISTRY,
)

ws_active_connections = Gauge(
    "bearings_ws_active_connections",
    "Currently connected agent WebSockets.",
    registry=REGISTRY,
)

ws_events_sent = Counter(
    "bearings_ws_events_sent_total",
    "AgentEvent frames sent to clients, by type.",
    ["type"],
    registry=REGISTRY,
)
