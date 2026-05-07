import responses
from core.market_data import MarketData


@responses.activate
def test_get_ohlcv_binance():
    responses.get(
        "https://api.binance.com/api/v3/klines",
        json=[[0, "50000", "50500", "49500", "50200", "100", 0, "100", 0, "0", "0", "0"]],
    )
    md = MarketData()
    df = md.get_ohlcv("BTCUSDT", "1h", 1)
    assert len(df) == 1
    assert "close" in df.columns
    assert "open" in df.columns
    assert "high" in df.columns
    assert "low" in df.columns
    assert "volume" in df.columns


@responses.activate
def test_get_price():
    responses.get(
        "https://api.binance.com/api/v3/ticker/price",
        json={"symbol": "BTCUSDT", "price": "65000.00"},
    )
    md = MarketData()
    price = md.get_price("BTCUSDT")
    assert price == 65000.0


@responses.activate
def test_coingecko_fallback_on_binance_failure():
    responses.get(
        "https://api.binance.com/api/v3/klines",
        body=Exception("Binance down"),
        status=500,
    )
    responses.get(
        "https://api.coingecko.com/api/v3/coins/btc/ohlc",
        json=[[1700000000000, 50000.0, 50500.0, 49800.0, 50200.0]],
    )
    md = MarketData()
    df = md.get_ohlcv("BTCUSDT", "1h", 200)
    assert len(df) == 1
    assert df.iloc[0]["open"] == 50000.0
    assert df.iloc[0]["high"] == 50500.0
    assert df.iloc[0]["low"] == 49800.0
    assert df.iloc[0]["close"] == 50200.0
