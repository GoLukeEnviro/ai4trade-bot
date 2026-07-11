import pytest

from rainbow.market_data.bitget import _normalize_symbol


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BTC", "BTCUSDT"),
        ("ETH", "ETHUSDT"),
        ("SOL", "SOLUSDT"),
        ("BTC/USDT", "BTCUSDT"),
        ("ETH/USDT", "ETHUSDT"),
        ("BTCUSDT", "BTCUSDT"),
        ("btc/usdt", "BTCUSDT"),
    ],
)
def test_normalize_symbol_appends_usdt_for_bare_assets(raw: str, expected: str) -> None:
    assert _normalize_symbol(raw) == expected
