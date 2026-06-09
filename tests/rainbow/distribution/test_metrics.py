"""Tests for rainbow.distribution.metrics — Prometheus metric definitions."""

from rainbow.distribution.metrics import (
    ACTIVE_COLLECTORS,
    COLLECTOR_CYCLE_DURATION,
    COLLECTOR_CYCLES,
    SIGNALS_COLLECTED,
    SIGNALS_SCORED,
    WEBHOOKS_DISPATCHED,
)


class TestMetricsExist:
    """Verify all Prometheus metrics are defined and have correct names.

    Note: prometheus_client strips the '_total' suffix from Counter metric names
    internally, so the _name attribute won't include it.
    """

    def test_signals_collected_name(self) -> None:
        assert SIGNALS_COLLECTED._name == "rainbow_signals_collected"

    def test_signals_collected_labels(self) -> None:
        assert SIGNALS_COLLECTED._labelnames == ("collector", "asset")

    def test_signals_scored_name(self) -> None:
        assert SIGNALS_SCORED._name == "rainbow_signals_scored"

    def test_signals_scored_labels(self) -> None:
        assert SIGNALS_SCORED._labelnames == ("asset",)

    def test_collector_cycles_name(self) -> None:
        assert COLLECTOR_CYCLES._name == "rainbow_collector_cycles"

    def test_collector_cycles_labels(self) -> None:
        assert COLLECTOR_CYCLES._labelnames == ("collector", "status")

    def test_collector_cycle_duration_name(self) -> None:
        assert COLLECTOR_CYCLE_DURATION._name == "rainbow_collector_cycle_duration_seconds"

    def test_collector_cycle_duration_labels(self) -> None:
        assert COLLECTOR_CYCLE_DURATION._labelnames == ("collector",)

    def test_active_collectors_name(self) -> None:
        assert ACTIVE_COLLECTORS._name == "rainbow_collectors_active"

    def test_webhooks_dispatched_name(self) -> None:
        assert WEBHOOKS_DISPATCHED._name == "rainbow_webhooks_dispatched"

    def test_webhooks_dispatched_labels(self) -> None:
        assert WEBHOOKS_DISPATCHED._labelnames == ("status",)


class TestMetricsIncrement:
    """Verify metrics accept increments without errors."""

    def test_signals_collected_increment(self) -> None:
        SIGNALS_COLLECTED.labels(collector="test", asset="BTC").inc()

    def test_signals_scored_increment(self) -> None:
        SIGNALS_SCORED.labels(asset="ETH").inc()

    def test_collector_cycles_increment(self) -> None:
        COLLECTOR_CYCLES.labels(collector="ta", status="success").inc()

    def test_collector_cycle_duration_observe(self) -> None:
        COLLECTOR_CYCLE_DURATION.labels(collector="ta").observe(1.5)

    def test_active_collectors_set(self) -> None:
        ACTIVE_COLLECTORS.set(3)

    def test_webhooks_dispatched_increment(self) -> None:
        WEBHOOKS_DISPATCHED.labels(status="success").inc()
