# tests/test_signal_router.py
from unittest.mock import MagicMock

from core.signal_model import Signal
from trading.signal_router import SignalRouter


def test_route_buy_to_ai4trade_calls_publish_and_returns_true():
    mock_publisher = MagicMock()
    mock_publisher.publish.return_value = True
    router = SignalRouter(publisher=mock_publisher)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=65000.0, quantity=0.1)
    success = router.route(signal, targets=["ai4trade", "log"])
    assert success is True
    mock_publisher.publish.assert_called_once_with(signal)


def test_route_sell_to_ai4trade_calls_publish_and_returns_true():
    mock_publisher = MagicMock()
    mock_publisher.publish.return_value = True
    router = SignalRouter(publisher=mock_publisher)
    signal = Signal(pair="ETH/USDT", action="SELL", confidence=80, price=3000.0, quantity=0.5)
    success = router.route(signal, targets=["ai4trade"])
    assert success is True
    mock_publisher.publish.assert_called_once_with(signal)


def test_route_returns_false_when_publisher_fails():
    mock_publisher = MagicMock()
    mock_publisher.publish.return_value = False
    router = SignalRouter(publisher=mock_publisher)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=70, price=65000.0, quantity=0.1)
    success = router.route(signal, targets=["ai4trade"])
    assert success is False
    mock_publisher.publish.assert_called_once()


def test_hold_signal_skips_publish_and_returns_true():
    mock_publisher = MagicMock()
    router = SignalRouter(publisher=mock_publisher)
    signal = Signal(pair="BTC/USDT", action="HOLD", confidence=50, price=65000.0, quantity=0)
    success = router.route(signal, targets=["ai4trade", "log"])
    assert success is True
    mock_publisher.publish.assert_not_called()


def test_log_target_only_does_not_call_publish():
    mock_publisher = MagicMock()
    router = SignalRouter(publisher=mock_publisher)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=65, price=65000.0, quantity=0.1)
    success = router.route(signal, targets=["log"])
    assert success is True
    mock_publisher.publish.assert_not_called()


def test_unknown_target_does_not_crash(caplog):
    mock_publisher = MagicMock()
    router = SignalRouter(publisher=mock_publisher)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=60, price=65000.0, quantity=0.1)
    success = router.route(signal, targets=["unknown_target"])
    assert success is True
    mock_publisher.publish.assert_not_called()
    assert any("unknown" in rec.message.lower() for rec in caplog.records)


def test_flush_queue_delegates_to_publisher():
    mock_publisher = MagicMock()
    mock_publisher.flush_queue.return_value = 3
    router = SignalRouter(publisher=mock_publisher)
    flushed = router.flush_queue()
    assert flushed == 3
    mock_publisher.flush_queue.assert_called_once()


def test_signal_router_does_not_instantiate_ai4trade_client():
    router = SignalRouter(publisher=MagicMock())
    assert not hasattr(router, "_client")
    assert hasattr(router, "_publisher")


def test_route_buy_to_rainbow_api_calls_publish_and_returns_true():
    mock_publisher = MagicMock()
    mock_publisher.publish.return_value = True
    mock_rainbow = MagicMock()
    mock_rainbow.publish.return_value = True
    router = SignalRouter(publisher=mock_publisher, rainbow_publisher=mock_rainbow)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=65000.0, quantity=0.1)
    success = router.route(signal, targets=["rainbow_api"])
    assert success is True
    mock_rainbow.publish.assert_called_once_with(signal)
    mock_publisher.publish.assert_not_called()


def test_rainbow_api_graceful_on_no_publisher(caplog):
    mock_publisher = MagicMock()
    mock_publisher.publish.return_value = True
    router = SignalRouter(publisher=mock_publisher, rainbow_publisher=None)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=65000.0, quantity=0.1)
    success = router.route(signal, targets=["rainbow_api", "log"])
    assert success is True
    assert any("kein RainbowApiPublisher" in rec.message for rec in caplog.records)


def test_rainbow_api_failure_does_not_block_other_targets():
    mock_publisher = MagicMock()
    mock_publisher.publish.return_value = True
    mock_rainbow = MagicMock()
    mock_rainbow.publish.return_value = False
    router = SignalRouter(publisher=mock_publisher, rainbow_publisher=mock_rainbow)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=65000.0, quantity=0.1)
    success = router.route(signal, targets=["ai4trade", "rainbow_api"])
    # ai4trade succeeds but rainbow fails — overall false because ai4trade success
    # but rainbow failure is graceful (logged, not blocking)
    mock_publisher.publish.assert_called_once()
    mock_rainbow.publish.assert_called_once()


def test_rainbow_api_and_ai4trade_both_targets():
    mock_publisher = MagicMock()
    mock_publisher.publish.return_value = True
    mock_rainbow = MagicMock()
    mock_rainbow.publish.return_value = True
    router = SignalRouter(publisher=mock_publisher, rainbow_publisher=mock_rainbow)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=80, price=65000.0, quantity=0.1)
    success = router.route(signal, targets=["ai4trade", "rainbow_api", "log"])
    assert success is True
    mock_publisher.publish.assert_called_once()
    mock_rainbow.publish.assert_called_once()

