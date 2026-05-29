import pytest

from exchanges.market_stream import (
    BitgetWebSocketStream,
    NoOpMarketStream,
    create_market_stream,
)


def test_noop_subscribe_does_not_raise():
    stream = NoOpMarketStream()
    stream.subscribe("BTCUSDT", callback=lambda x: x)


def test_noop_unsubscribe_does_not_raise():
    stream = NoOpMarketStream()
    stream.unsubscribe("BTCUSDT")


def test_noop_close_does_not_raise():
    stream = NoOpMarketStream()
    stream.close()


def test_create_market_stream_rest_returns_noop():
    stream = create_market_stream("rest")
    assert isinstance(stream, NoOpMarketStream)


def test_create_market_stream_bitget_ws_raises():
    with pytest.raises(NotImplementedError):
        create_market_stream("bitget_ws")


def test_create_market_stream_unknown_raises():
    with pytest.raises(ValueError, match="Unbekannter Stream-Provider"):
        create_market_stream("bogus")


def test_bitget_websocket_stream_init_raises():
    with pytest.raises(NotImplementedError, match="noch nicht implementiert"):
        BitgetWebSocketStream()
