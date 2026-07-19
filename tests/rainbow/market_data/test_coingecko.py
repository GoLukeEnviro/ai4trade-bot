"""Tests for rainbow.market_data.coingecko — CoinGeckoClient."""

from unittest.mock import AsyncMock, patch

import pytest

from rainbow.exceptions import ProviderError
from rainbow.market_data.coingecko import (
    CoinGeckoClient,
    _normalize_timestamp,
    _symbol_to_coin_id,
)


class TestSymbolToCoinId:
    def test_basic_symbol(self) -> None:
        assert _symbol_to_coin_id("BTC") == "btc"

    def test_strips_usdt(self) -> None:
        assert _symbol_to_coin_id("BTCUSDT") == "btc"

    def test_strips_slash(self) -> None:
        # _symbol_to_coin_id strips both "usdt" and "/" characters
        # "BTC/USDT" -> strip "/" -> "BTCUSDT" -> strip "usdt" -> "btc"
        assert _symbol_to_coin_id("BTC/USDT") == "btc"

    def test_lowercase(self) -> None:
        assert _symbol_to_coin_id("eth") == "eth"


class TestNormalizeTimestamp:
    def test_milliseconds(self) -> None:
        # 1700000000000 ms => ~1700000000 seconds
        result = _normalize_timestamp(1700000000000)
        assert result == 1700000000.0

    def test_seconds(self) -> None:
        result = _normalize_timestamp(1700000000)
        assert result == 1700000000.0

    def test_negative_returns_none(self) -> None:
        assert _normalize_timestamp(-1) is None

    def test_zero_returns_none(self) -> None:
        assert _normalize_timestamp(0) is None

    def test_invalid_string_returns_none(self) -> None:
        assert _normalize_timestamp("abc") is None

    def test_none_returns_none(self) -> None:
        assert _normalize_timestamp(None) is None

    def test_small_value_returns_none(self) -> None:
        # Values too small to be valid timestamps
        assert _normalize_timestamp(100) is None


class TestCoinGeckoConstruction:
    def test_default_construction(self) -> None:
        client = CoinGeckoClient()
        assert client._base_url == "https://api.coingecko.com/api/v3"

    def test_custom_base_url(self) -> None:
        client = CoinGeckoClient(base_url="https://custom.api.com/v3/")
        assert client._base_url == "https://custom.api.com/v3"  # trailing slash stripped


class TestCoinGeckoHealthCheck:
    async def test_health_check_success(self) -> None:
        client = CoinGeckoClient()
        with patch.object(client, "_request", return_value={"gecko_says": "To the Moon!"}):
            result = await client.health_check()
            assert result is True

    async def test_health_check_failure(self) -> None:
        client = CoinGeckoClient()
        with patch.object(client, "_request", side_effect=ProviderError("coingecko", "fail")):
            result = await client.health_check()
            assert result is False


class TestCoinGeckoGetPrice:
    async def test_get_price_success(self) -> None:
        client = CoinGeckoClient()
        with patch.object(client, "_request", return_value={"btc": {"usd": 50000.0}}):
            price = await client.get_price("BTC")
            assert price == 50000.0

    async def test_get_price_missing_data_raises(self) -> None:
        client = CoinGeckoClient()
        with patch.object(client, "_request", return_value={}), pytest.raises(ProviderError, match="Keine Preisdaten"):
            await client.get_price("BTC")


class TestCoinGeckoGetOhlcv:
    async def test_get_ohlcv_success(self) -> None:
        client = CoinGeckoClient()
        ohlcv_data = [
            [1700000000000, 42000.0, 42500.0, 41500.0, 42200.0],
            [1700003600000, 42200.0, 42800.0, 42000.0, 42600.0],
        ]
        with patch.object(client, "_request", return_value=ohlcv_data):
            df = await client.get_ohlcv("BTC", "1h", limit=10)
            assert "close" in df.columns
            assert len(df) == 2


class TestCoinGeckoRequest:
    async def test_request_raises_after_max_retries(self) -> None:
        import httpx

        client = CoinGeckoClient()
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        client._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock), pytest.raises(ProviderError, match="gescheitert"):
            await client._request("/test", max_retries=2)
