"""Prometheus instrument bundle + text-exposition renderer.

Per ``docs/architecture-v1.md`` §1.1.7 the metrics package owns
instrumentation; per arch §1.1.5 ``web/routes/metrics.py`` exposes
``GET /metrics`` and delegates rendering here. The bundle lives on a
**per-app** :class:`prometheus_client.CollectorRegistry` rather than
the global default — that lets parallel test runs construct fresh
apps without clashing on metric registration (the global registry
disallows duplicate-name registration).
"""

from __future__ import annotations

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    generate_latest,
)

from bearings.config.constants import (
    METRIC_NAME_ACTIVE_DRIVERS,
    METRIC_NAME_ACTIVE_RUNNERS,
    METRIC_NAME_ADVISOR_CALLS_TOTAL,
    METRIC_NAME_INFO,
    METRIC_NAME_QUEUED_PROMPTS,
    METRIC_NAME_QUOTA_OVERALL,
    METRIC_NAME_QUOTA_SONNET,
    METRIC_NAME_ROUTING_DECISIONS_TOTAL,
    METRIC_NAME_UPTIME_SECONDS,
)


class BearingsMetrics:
    """Owns a per-app :class:`CollectorRegistry` plus named instruments.

    The constructor accepts the running version so the
    ``bearings_info`` build-info gauge can carry it as a label;
    follows the well-known Prometheus pattern (``<app>_info{version="..."}``
    = 1).
    """

    def __init__(self, *, version: str) -> None:
        self._registry = CollectorRegistry()

        # Build-info gauge — Prometheus pattern: a constant 1 with a
        # ``version`` label so a Grafana panel can group by version.
        self.info = Gauge(
            METRIC_NAME_INFO,
            "Build info for the Bearings process.",
            labelnames=("version",),
            registry=self._registry,
        )
        self.info.labels(version=version).set(1)

        # Process uptime — seconds since :func:`build_app` finished
        # construction. The route handler sets this on every scrape.
        self.uptime_seconds = Gauge(
            METRIC_NAME_UPTIME_SECONDS,
            "Seconds since the FastAPI app was constructed.",
            registry=self._registry,
        )

        # Live-state gauges: filled by the route handler from app.state
        # immediately before rendering so the wire response reflects
        # the current runtime.
        self.active_runners = Gauge(
            METRIC_NAME_ACTIVE_RUNNERS,
            "Number of session runners currently registered.",
            registry=self._registry,
        )
        self.queued_prompts = Gauge(
            METRIC_NAME_QUEUED_PROMPTS,
            "Total queued user prompts across all session runners.",
            registry=self._registry,
        )
        self.active_drivers = Gauge(
            METRIC_NAME_ACTIVE_DRIVERS,
            "Number of auto-driver runs currently registered.",
            registry=self._registry,
        )

        # Quota-poll gauges (spec §4). NaN-when-unset is the Prometheus
        # convention for "not-yet-observed" gauge values; the
        # prometheus_client library exposes ``set_to_current_time`` /
        # ``set`` only, so the route handler skips the ``set`` call
        # when no snapshot exists and the gauge stays at 0 (the
        # absence of the metric in a freshly-constructed registry
        # would be cleaner but the library forces an initial value).
        self.quota_overall_used_pct = Gauge(
            METRIC_NAME_QUOTA_OVERALL,
            "Latest overall_used_pct from the quota poller.",
            registry=self._registry,
        )
        self.quota_sonnet_used_pct = Gauge(
            METRIC_NAME_QUOTA_SONNET,
            "Latest sonnet_used_pct from the quota poller.",
            registry=self._registry,
        )

        # Counters per spec §8. The aggregator route reads the
        # messages table directly; this counter mirrors that (the
        # route handler sets it on each scrape from a fresh aggregate).
        # Keeping it as a Gauge would lie about the semantic — it IS
        # a counter (monotonic increasing) — so we use ``Counter``
        # with ``inc`` deltas. The route layer maintains a per-source
        # last-seen total and increments by the diff so the wire
        # value stays monotonic across scrapes.
        self.routing_decisions_total = Counter(
            METRIC_NAME_ROUTING_DECISIONS_TOTAL,
            "Cumulative routing decisions made, by source.",
            labelnames=("source",),
            registry=self._registry,
        )
        self.advisor_calls_total = Counter(
            METRIC_NAME_ADVISOR_CALLS_TOTAL,
            "Cumulative advisor primitive invocations.",
            registry=self._registry,
        )

    @property
    def registry(self) -> CollectorRegistry:
        """The :class:`CollectorRegistry` underpinning every instrument."""
        return self._registry


def render_metrics(metrics: BearingsMetrics) -> bytes:
    """Render the registry in Prometheus 0.0.4 text exposition format.

    Returns ``bytes`` because that is what
    :class:`fastapi.responses.Response` expects when
    ``media_type=METRICS_CONTENT_TYPE``; the prometheus_client library
    already returns bytes from :func:`generate_latest` so no
    re-encoding is needed.
    """
    return generate_latest(metrics.registry)


__all__ = ["BearingsMetrics", "render_metrics"]
