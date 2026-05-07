from unittest.mock import MagicMock

from core.signal_model import Signal
from adapters.signal_publisher import SignalPublisher


def test_publish_success():
    mock_client = MagicMock()
    mock_client.publish_signal.return_value = {"success": True}
    sp = SignalPublisher(client=mock_client)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=65000.0, quantity=0.1)
    assert sp.publish(signal) is True
    assert len(sp.queue) == 0


def test_publish_failure_queues():
    mock_client = MagicMock()
    mock_client.publish_signal.return_value = {"success": False}
    sp = SignalPublisher(client=mock_client)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=65000.0, quantity=0.1)
    assert sp.publish(signal) is False
    assert len(sp.queue) == 1


def test_publish_exception_queues():
    mock_client = MagicMock()
    mock_client.publish_signal.side_effect = ConnectionError("network error")
    sp = SignalPublisher(client=mock_client)
    signal = Signal(pair="ETH/USDT", action="SELL", confidence=80, price=3000.0, quantity=1.5)
    assert sp.publish(signal) is False
    assert len(sp.queue) == 1


def test_flush_does_not_duplicate_on_failure():
    mock_client = MagicMock()
    mock_client.publish_signal.return_value = {"success": False}
    sp = SignalPublisher(client=mock_client)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=65000.0, quantity=0.1)
    sp.publish(signal)
    assert len(sp.queue) == 1
    sp.flush_queue()
    assert len(sp.queue) == 1


def test_flush_succeeds_after_initial_failure():
    mock_client = MagicMock()
    mock_client.publish_signal.side_effect = [{"success": False}, {"success": True}]
    sp = SignalPublisher(client=mock_client)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=65000.0, quantity=0.1)
    sp.publish(signal)
    assert len(sp.queue) == 1
    flushed = sp.flush_queue()
    assert flushed == 1
    assert len(sp.queue) == 0


def test_queue_overflow_drops_oldest():
    mock_client = MagicMock()
    mock_client.publish_signal.return_value = {"success": False}
    sp = SignalPublisher(client=mock_client, max_queue=2)
    for i in range(4):
        sp.publish(Signal(pair="BTC/USDT", action="BUY", confidence=70 + i, price=65000.0, quantity=0.1))
    assert len(sp.queue) == 2
    assert sp.queue[0]["confidence"] == 72


def test_send_converts_pair_to_symbol():
    mock_client = MagicMock()
    mock_client.publish_signal.return_value = {"success": True}
    sp = SignalPublisher(client=mock_client)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=65000.0, quantity=0.1)
    sp.publish(signal)
    mock_client.publish_signal.assert_called_once()
    call_kwargs = mock_client.publish_signal.call_args
    assert call_kwargs.kwargs["symbol"] == "BTCUSDT"
