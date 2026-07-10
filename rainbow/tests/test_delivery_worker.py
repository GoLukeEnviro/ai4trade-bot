from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from rainbow.delivery.__main__ import build_worker
from rainbow.delivery.client import AuthenticationDeliveryError, PermanentDeliveryError, RetryableDeliveryError
from rainbow.delivery.models import AssetRoute, DeliveryConfig, DeliveryMode
from rainbow.delivery.outbox import DeliveryOutbox
from rainbow.delivery.policy import DeliveryPolicy
from rainbow.delivery.worker import DeliveryWorker


def _signal(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    signal: dict[str, object] = {
        "signal_id": "signal-1",
        "timestamp": now,
        "source": "ta_1h",
        "asset": "BTC",
        "signal_type": "technical",
        "direction": "bullish",
        "strength": 0.8,
        "confidence": 0.8,
        "value": 60_000.0,
        "metadata": {"canonical_symbol": "BTC/USDT:USDT", "timeframe": "1h"},
    }
    signal.update(overrides)
    return signal


def _config(mode: DeliveryMode, db_path: str) -> DeliveryConfig:
    return DeliveryConfig(
        mode=mode,
        outbox_path=db_path,
        asset_routes={"BTC": AssetRoute(ai4trade_symbol="BTCUSDT", quantity=0.1)},
    )


def test_policy_maps_bullish_technical_signal_to_ai4trade_payload() -> None:
    policy = DeliveryPolicy(_config(DeliveryMode.SHADOW, ":memory:"))

    result = policy.evaluate(_signal(), now=datetime.now(UTC))

    assert result.payload is not None
    assert result.payload.action == "BUY"
    assert result.payload.symbol == "BTCUSDT"
    assert result.payload.price == 60_000.0


def test_policy_maps_low_strength_bearish_technical_signal_to_sell() -> None:
    policy = DeliveryPolicy(_config(DeliveryMode.SHADOW, ":memory:"))

    result = policy.evaluate(
        _signal(direction="bearish", strength=0.3, confidence=0.3),
        now=datetime.now(UTC),
    )

    assert result.payload is not None
    assert result.payload.action == "SELL"


@pytest.mark.parametrize(
    ("direction", "strength"),
    [("bullish", 0.65), ("bearish", 0.35)],
)
def test_policy_keeps_legacy_threshold_boundaries_as_hold(direction: str, strength: float) -> None:
    policy = DeliveryPolicy(_config(DeliveryMode.SHADOW, ":memory:"))

    result = policy.evaluate(
        _signal(direction=direction, strength=strength, confidence=strength),
        now=datetime.now(UTC),
    )

    assert result.payload is None
    assert result.reason == "hold_signal"


def test_policy_rejects_non_technical_value_as_a_price() -> None:
    policy = DeliveryPolicy(_config(DeliveryMode.SHADOW, ":memory:"))

    result = policy.evaluate(_signal(signal_type="news", value=60_000.0), now=datetime.now(UTC))

    assert result.payload is None
    assert result.reason == "non_technical_signal"


def test_policy_rejects_stale_signal() -> None:
    policy = DeliveryPolicy(_config(DeliveryMode.SHADOW, ":memory:"))
    old_timestamp = (datetime.now(UTC) - timedelta(seconds=901)).isoformat()

    result = policy.evaluate(_signal(timestamp=old_timestamp), now=datetime.now(UTC))

    assert result.payload is None
    assert result.reason == "stale_signal"


class _Provider:
    def __init__(self, signals: list[dict[str, object]]) -> None:
        self.signals = signals
        self.calls = 0

    async def fetch_latest(self) -> list[dict[str, object]]:
        self.calls += 1
        return self.signals


class _Sender:
    def __init__(self) -> None:
        self.payloads = []

    async def publish(self, payload) -> None:
        self.payloads.append(payload)


@pytest.mark.anyio
async def test_off_mode_does_not_read_or_send_signals(tmp_path) -> None:
    provider = _Provider([_signal()])
    sender = _Sender()
    worker = DeliveryWorker(_config(DeliveryMode.OFF, str(tmp_path / "outbox.db")), provider, sender)

    result = await worker.run_once()

    assert provider.calls == 0
    assert sender.payloads == []
    assert result.mode == DeliveryMode.OFF


@pytest.mark.anyio
async def test_shadow_mode_persists_evidence_without_external_send(tmp_path) -> None:
    provider = _Provider([_signal()])
    sender = _Sender()
    worker = DeliveryWorker(_config(DeliveryMode.SHADOW, str(tmp_path / "outbox.db")), provider, sender)

    result = await worker.run_once()

    assert result.shadowed == 1
    assert sender.payloads == []
    assert await worker.outbox.count_by_status("shadow") == 1
    await worker.close()


@pytest.mark.anyio
async def test_live_mode_sends_pending_payload_once(tmp_path) -> None:
    provider = _Provider([_signal()])
    sender = _Sender()
    worker = DeliveryWorker(_config(DeliveryMode.LIVE, str(tmp_path / "outbox.db")), provider, sender)

    result = await worker.run_once()

    assert result.sent == 1
    assert len(sender.payloads) == 1
    assert await worker.outbox.count_by_status("sent") == 1
    await worker.close()


class _RetryingSender:
    async def publish(self, payload) -> None:
        raise RetryableDeliveryError("temporary outage")


class _AuthFailingSender:
    async def publish(self, payload) -> None:
        raise AuthenticationDeliveryError("expired token")


class _PermanentFailingSender:
    async def publish(self, payload) -> None:
        raise PermanentDeliveryError("invalid payload")


class _Heartbeat:
    def __init__(self) -> None:
        self.calls = 0

    async def poll_once(self) -> None:
        self.calls += 1


class _TaskHandler:
    def __init__(self) -> None:
        self.calls = 0

    async def process_pending(self) -> int:
        self.calls += 1
        return 0


@pytest.mark.anyio
async def test_retryable_failure_keeps_payload_for_later_retry(tmp_path) -> None:
    worker = DeliveryWorker(
        _config(DeliveryMode.LIVE, str(tmp_path / "outbox.db")),
        _Provider([_signal()]),
        _RetryingSender(),
    )

    result = await worker.run_once()

    assert result.retried == 1
    assert await worker.outbox.count_by_status("retrying") == 1
    await worker.close()


@pytest.mark.anyio
async def test_auth_failure_degrades_worker_without_raising(tmp_path) -> None:
    worker = DeliveryWorker(
        _config(DeliveryMode.LIVE, str(tmp_path / "outbox.db")),
        _Provider([_signal()]),
        _AuthFailingSender(),
    )

    result = await worker.run_once()

    assert result.auth_failed is True
    assert await worker.outbox.count_by_status("dead_letter") == 1
    await worker.close()


@pytest.mark.anyio
async def test_permanent_failure_moves_payload_to_dead_letter(tmp_path) -> None:
    worker = DeliveryWorker(
        _config(DeliveryMode.LIVE, str(tmp_path / "outbox.db")),
        _Provider([_signal()]),
        _PermanentFailingSender(),
    )

    result = await worker.run_once()

    assert result.dead_lettered == 1
    assert await worker.outbox.count_by_status("dead_letter") == 1
    await worker.close()


@pytest.mark.anyio
async def test_enabled_heartbeat_and_task_handler_run_inside_worker(tmp_path) -> None:
    heartbeat = _Heartbeat()
    task_handler = _TaskHandler()
    config = _config(DeliveryMode.SHADOW, str(tmp_path / "outbox.db"))
    config.heartbeat_enabled = True
    worker = DeliveryWorker(
        config,
        _Provider([_signal()]),
        _Sender(),
        heartbeat=heartbeat,
        task_handler=task_handler,
    )

    await worker.run_once()

    assert heartbeat.calls == 1
    assert task_handler.calls == 1
    await worker.close()


@pytest.mark.anyio
async def test_shadow_worker_factory_does_not_require_ai4trade_token(tmp_path) -> None:
    config = _config(DeliveryMode.SHADOW, str(tmp_path / "outbox.db"))

    worker = build_worker(config)

    assert worker.config.token == ""
    await worker.close()


@pytest.mark.anyio
async def test_outbox_keeps_delivery_after_reopen(tmp_path) -> None:
    path = str(tmp_path / "outbox.db")
    outbox = DeliveryOutbox(path)
    await outbox.start()
    await outbox.enqueue(
        DeliveryPolicy(_config(DeliveryMode.LIVE, path)).evaluate(_signal(), now=datetime.now(UTC)).payload,
        status="pending",
    )
    await outbox.close()

    reopened = DeliveryOutbox(path)
    await reopened.start()

    assert await reopened.count_by_status("pending") == 1
    await reopened.close()
