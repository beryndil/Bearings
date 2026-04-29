"""Bearings metrics package — Prometheus instruments + collector.

Per ``docs/architecture-v1.md`` §1.1.7 ``bearings.metrics`` is the
instrumentation home; spec §8 telemetry counters (advisor calls,
override events, quota-downgrade events) and the misc-API metrics
(item 1.10) live here so the surface has room to grow without
bloating one file.

The package exposes:

* :class:`BearingsMetrics` — owns a per-app
  :class:`prometheus_client.CollectorRegistry` plus the named
  :class:`Counter` / :class:`Gauge` instances.
* :func:`render_metrics` — renders the registry as Prometheus 0.0.4
  text exposition for the ``GET /metrics`` route.

A per-app registry (rather than the global default) keeps parallel
test runs from racing on metric registration.
"""

from __future__ import annotations

from bearings.metrics.collector import BearingsMetrics, render_metrics

__all__ = ["BearingsMetrics", "render_metrics"]
