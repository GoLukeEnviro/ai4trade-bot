import pytest
import responses

from exchanges.bitget_rest import BitgetRestClient


@responses.activate
def test_get_ohlcv_success():
    responses.get(
        "https://api.bitget.com/api/v2/spot/market/candles",
        json={
            "code": "00000",
            "msg": "success",
            "data": [
                ["1700000000000", "50000.0", "50500.0", "49500.0", "50200.0", "100.5", "5000000"],
                ["1700003600000", "50200.0", "50800.0", "50100.0", "50600.0", "120.3", "6000000"],
            ],
        },
    )
    client = BitgetRestClient()
    df = client.get_ohlcv("BTCUSDT", "1h", 2)
    assert len(df) == 2
    assert df.iloc[0]["open"] == 50000.0
    assert df.iloc[0]["high"] == 50500.0
    assert df.iloc[0]["low"] == 49500.0
    assert df.iloc[0]["close"] == 50200.0
    assert df.iloc[0]["volume"] == 100.5


@responses.activate
def test_get_ohlcv_error_code_triggers_retry():
    # First two responses: error code, third: success
    responses.get(
        "https://api.bitget.com/api/v2/spot/market/candles",
        json={"code": "50001", "msg": "rate limit"},
        status=200,
    )
    responses.get(
        "https://api.bitget.com/api/v2/spot/market/candles",
        json={"code": "50001", "msg": "rate limit"},
        status=200,
    )
    responses.get(
        "https://api.bitget.com/api/v2/spot/market/candles",
        json={
            "code": "00000",
            "msg": "success",
            "data": [["1700000000000", "50000.0", "50500.0", "49500.0", "50200.0", "100.0", "5000000"]],
        },
    )
    client = BitgetRestClient()
    df = client.get_ohlcv("BTCUSDT", "1h", 1)
    assert len(df) == 1
    assert len(responses.calls) == 3


@responses.activate
def test_get_price_success():
    responses.get(
        "https://api.bitget.com/api/v2/spot/market/tickers",
        json={"code": "00000", "data": [{"symbol": "BTCUSDT", "lastPr": "65000.00"}]},
    )
    client = BitgetRestClient()
    price = client.get_price("BTCUSDT")
    assert price == 65000.0


@responses.activate
def test_get_price_empty_data_raises():
    responses.get(
        "https://api.bitget.com/api/v2/spot/market/tickers",
        json={"code": "00000", "data": []},
    )
    client = BitgetRestClient()
    with pytest.raises(ValueError, match="Keine Ticker-Daten"):
        client.get_price("BTCUSDT")


def test_symbol_normalization():
    assert BitgetRestClient._normalize_symbol("BTC/USDT") == "BTCUSDT"
    assert BitgetRestClient._normalize_symbol("ETH/USDT") == "ETHUSDT"
    assert BitgetRestClient._normalize_symbol("BTCUSDT") == "BTCUSDT"
