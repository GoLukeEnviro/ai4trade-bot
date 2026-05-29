import pytest

from exchanges.bitget_rest import BitgetRestClient
from exchanges.factory import create_exchange


def test_default_returns_bitget():
    exchange = create_exchange()
    assert isinstance(exchange, BitgetRestClient)


def test_explicit_bitget():
    exchange = create_exchange("bitget")
    assert isinstance(exchange, BitgetRestClient)


def test_unknown_raises():
    with pytest.raises(ValueError, match="Unbekannter Exchange-Provider: ftx"):
        create_exchange("ftx")
