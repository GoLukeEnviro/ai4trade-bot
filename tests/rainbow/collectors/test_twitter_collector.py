"""Tests for rainbow.collectors.twitter_collector — TwitterCollector."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from rainbow.collectors.twitter_collector import TwitterCollector
from rainbow.exceptions import CollectorError
from rainbow.models.signal import Direction, SignalType


def _twitter_response(tweets: list[dict]) -> dict:
    """Build a mock Twitter API response."""
    return {"data": tweets}


def _make_http_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response that supports sync .json()."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def collector() -> TwitterCollector:
    return TwitterCollector(bearer_token="test-token", assets=["BTC"])


class TestTwitterCollectorConstruction:
    def test_default_construction_no_token(self) -> None:
        c = TwitterCollector()
        assert c.name == "twitter"
        assert c._bearer_token == ""
        assert c._assets == ["BTC", "ETH"]

    def test_custom_construction(self) -> None:
        c = TwitterCollector(
            bearer_token="my-token",
            assets=["SOL"],
            max_results=50,
        )
        assert c._bearer_token == "my-token"
        assert c._assets == ["SOL"]
        assert c._max_results == 50


class TestTwitterCollectorCollect:
    async def test_collect_returns_signal(self, collector: TwitterCollector) -> None:
        tweets_data = [
            {"text": "Bitcoin bullish moon rally", "public_metrics": {"like_count": 10, "retweet_count": 5}},
            {"text": "Generic text without keywords", "public_metrics": {"like_count": 1, "retweet_count": 0}},
        ]
        collector._client = AsyncMock()
        resp = _make_http_response(_twitter_response(tweets_data))
        collector._client.get.return_value = resp

        signals = await collector.collect()
        assert len(signals) >= 1
        assert signals[0].signal_type == SignalType.SOCIAL

    async def test_collect_no_bearer_token_returns_empty(self) -> None:
        collector = TwitterCollector(bearer_token="")
        signals = await collector.collect()
        assert signals == []

    async def test_collect_twitter_rate_limit(self, collector: TwitterCollector) -> None:
        collector._client = AsyncMock()
        resp = _make_http_response({}, status_code=429)
        collector._client.get.return_value = resp

        result = await collector._search_recent("BTC")
        assert result == []

    async def test_collect_twitter_unauthorized_raises(self, collector: TwitterCollector) -> None:
        collector._client = AsyncMock()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 401
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=resp
        )
        collector._client.get.return_value = resp

        with pytest.raises(CollectorError, match="Unauthorized"):
            await collector._search_recent("BTC")


class TestTwitterCollectorAnalysis:
    def test_analyze_tweets_bullish(self) -> None:
        collector = TwitterCollector(bearer_token="t")
        tweets = [
            {"text": "Bitcoin bullish moon rally surge", "public_metrics": {"like_count": 5, "retweet_count": 2}},
        ]
        signal = collector._analyze_tweets(tweets, "BTC")
        assert signal is not None
        assert signal.direction == Direction.BULLISH
        assert signal.asset == "BTC"

    def test_analyze_tweets_bearish(self) -> None:
        collector = TwitterCollector(bearer_token="t")
        tweets = [
            {"text": "Bitcoin crash dump sell short", "public_metrics": {"like_count": 3, "retweet_count": 1}},
        ]
        signal = collector._analyze_tweets(tweets, "BTC")
        assert signal is not None
        assert signal.direction == Direction.BEARISH

    def test_analyze_tweets_empty(self) -> None:
        collector = TwitterCollector(bearer_token="t")
        result = collector._analyze_tweets([], "BTC")
        assert result is None

    def test_analyze_tweets_neutral(self) -> None:
        collector = TwitterCollector(bearer_token="t")
        tweets = [
            {"text": "some generic text", "public_metrics": {"like_count": 0, "retweet_count": 0}},
        ]
        signal = collector._analyze_tweets(tweets, "BTC")
        assert signal is not None
        assert signal.direction == Direction.NEUTRAL
        assert signal.strength == 0.3


class TestTwitterCollectorHealthCheck:
    async def test_health_check_no_token(self) -> None:
        collector = TwitterCollector(bearer_token="")
        assert await collector.health_check() is False

    async def test_health_check_success(self) -> None:
        collector = TwitterCollector(bearer_token="token")
        collector._client = AsyncMock()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        collector._client.get.return_value = resp

        assert await collector.health_check() is True

    async def test_health_check_http_error(self) -> None:
        collector = TwitterCollector(bearer_token="token")
        collector._client = AsyncMock()
        collector._client.get.side_effect = httpx.HTTPError("fail")

        assert await collector.health_check() is False
