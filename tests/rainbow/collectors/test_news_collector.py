"""Tests for rainbow.collectors.news_collector — NewsCollector."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from rainbow.collectors.news_collector import NewsCollector
from rainbow.models.signal import CryptoSignal, Direction, SignalType


@pytest.fixture
def mock_response() -> dict:
    """Minimal CryptoCompare news API response."""
    return {
        "Data": [
            {
                "title": "Bitcoin bullish rally surges to new heights",
                "body": "BTC shows strong growth.",
                "categories": "BTC|Trading",
            },
            {
                "title": "Ethereum hack exploited in scam",
                "body": "ETH hack causes concern.",
                "categories": "ETH|Security",
            },
            {
                "title": "Generic crypto news with no relevant keywords",
                "body": "Something happened.",
                "categories": "",
            },
        ]
    }


def _make_http_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response that supports .json() (sync) and .raise_for_status()."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp


class TestNewsCollectorConstruction:
    def test_default_construction(self) -> None:
        collector = NewsCollector()
        assert collector.name == "news"
        assert collector._assets == ["BTC", "ETH", "SOL"]
        assert collector._max_articles == 20

    def test_custom_construction(self) -> None:
        collector = NewsCollector(
            assets=["DOGE"],
            cryptocompare_base="https://example.com",
            max_articles=5,
        )
        assert collector._assets == ["DOGE"]
        assert collector._cryptocompare_base == "https://example.com"
        assert collector._max_articles == 5


class TestNewsCollectorCollect:
    async def test_collect_returns_signals(self, mock_response: dict) -> None:
        collector = NewsCollector(assets=["BTC", "ETH"])
        collector._client = AsyncMock()
        resp = _make_http_response(mock_response)
        collector._client.get.return_value = resp

        signals = await collector.collect()
        assert len(signals) >= 1
        assert all(isinstance(s, CryptoSignal) for s in signals)

    async def test_collect_filters_btc(self, mock_response: dict) -> None:
        collector = NewsCollector(assets=["BTC"])
        collector._client = AsyncMock()
        resp = _make_http_response(mock_response)
        collector._client.get.return_value = resp

        signals = await collector.collect()
        btc_signals = [s for s in signals if s.asset == "BTC"]
        assert len(btc_signals) >= 1
        assert btc_signals[0].signal_type == SignalType.NEWS

    async def test_collect_empty_api_response(self) -> None:
        collector = NewsCollector()
        collector._client = AsyncMock()
        resp = _make_http_response({"Data": []})
        collector._client.get.return_value = resp

        signals = await collector.collect()
        assert signals == []

    async def test_collect_timeout_returns_empty(self) -> None:
        collector = NewsCollector()
        collector._client = AsyncMock()
        collector._client.get.side_effect = httpx.TimeoutException("timeout")

        signals = await collector.collect()
        assert signals == []


class TestNewsCollectorAnalysis:
    def test_analyze_articles_bullish(self) -> None:
        collector = NewsCollector()
        articles = [
            {"title": "Bitcoin bullish rally", "body": "surge soar", "categories": ""},
        ]
        result = collector._analyze_articles(articles, "BTC")
        assert result is not None
        assert result.direction == Direction.BULLISH
        assert result.asset == "BTC"

    def test_analyze_articles_bearish(self) -> None:
        collector = NewsCollector()
        articles = [
            {"title": "Bitcoin crash dump", "body": "plunge scam", "categories": ""},
        ]
        result = collector._analyze_articles(articles, "BTC")
        assert result is not None
        assert result.direction == Direction.BEARISH

    def test_analyze_articles_empty(self) -> None:
        collector = NewsCollector()
        result = collector._analyze_articles([], "BTC")
        assert result is None

    def test_filter_for_asset_match(self) -> None:
        collector = NewsCollector()
        articles = [
            {"title": "Bitcoin price up", "body": ""},
            {"title": "Unrelated article", "body": "nothing relevant"},
        ]
        filtered = collector._filter_for_asset(articles, "BTC")
        assert len(filtered) == 1

    def test_filter_for_asset_no_match(self) -> None:
        collector = NewsCollector()
        articles = [
            {"title": "Stock market rises", "body": "Nothing about crypto."},
        ]
        filtered = collector._filter_for_asset(articles, "BTC")
        assert len(filtered) == 0


class TestNewsCollectorHealthCheck:
    async def test_health_check_success(self) -> None:
        collector = NewsCollector()
        collector._client = AsyncMock()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        collector._client.get.return_value = resp

        assert await collector.health_check() is True

    async def test_health_check_failure(self) -> None:
        collector = NewsCollector()
        collector._client = AsyncMock()
        collector._client.get.side_effect = httpx.HTTPError("fail")

        assert await collector.health_check() is False
