from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

SIGNALS_COLLECTED = Counter(
    "rainbow_signals_collected_total",
    "Signals collected",
    ["collector", "asset"],
)

SIGNALS_SCORED = Counter(
    "rainbow_signals_scored_total",
    "Signals scored",
    ["asset"],
)

COLLECTOR_CYCLES = Counter(
    "rainbow_collector_cycles_total",
    "Collector collection cycles",
    ["collector", "status"],
)

COLLECTOR_CYCLE_DURATION = Histogram(
    "rainbow_collector_cycle_duration_seconds",
    "Collector cycle duration",
    ["collector"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30),
)

ACTIVE_COLLECTORS = Gauge(
    "rainbow_collectors_active",
    "Number of active collectors",
)

WEBHOOKS_DISPATCHED = Counter(
    "rainbow_webhooks_dispatched_total",
    "Webhook dispatches",
    ["status"],
)
