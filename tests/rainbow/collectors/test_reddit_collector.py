"""Tests for rainbow.collectors.reddit_collector — RedditCollector."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from rainbow.collectors.reddit_collector import RedditCollector
from rainbow.models.signal import Direction, SignalType


def _reddit_response(titles: list[str]) -> dict:
    """Build a mock Reddit API response with given post titles."""
    children = [
        {"data": {"title": t, "score": 10, "-ups": 10}} for t in titles
    ]
    return {"data": {"children": children}}


def _make_http_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response that supports sync .json()."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def collector() -> RedditCollector:
    return RedditCollector(assets=["BTC"], posts_per_subreddit=5)


class TestRedditCollectorConstruction:
    def test_default_construction(self) -> None:
        c = RedditCollector()
        assert c.name == "reddit"
        assert c._assets == ["BTC", "ETH", "SOL"]

    def test_custom_construction(self) -> None:
        c = RedditCollector(
            assets=["DOGE"],
            subreddits={"DOGE": ["dogecoin"]},
            posts_per_subreddit=10,
        )
        assert c._assets == ["DOGE"]
        assert c._subreddits == {"DOGE": ["dogecoin"]}


class TestRedditCollectorCollect:
    async def test_collect_bullish_signal(self, collector: RedditCollector) -> None:
        collector._client = AsyncMock()
        response = _reddit_response(["Bitcoin bullish moon rally", "More crypto stuff"])
        resp = _make_http_response(response)
        collector._client.get.return_value = resp

        signals = await collector.collect()
        assert len(signals) >= 1
        assert signals[0].signal_type == SignalType.SOCIAL
        assert signals[0].asset == "BTC"

    async def test_collect_empty_subreddit(self, collector: RedditCollector) -> None:
        collector._client = AsyncMock()
        resp = _make_http_response({"data": {"children": []}})
        collector._client.get.return_value = resp

        signals = await collector.collect()
        assert signals == []

    async def test_collect_rate_limit_returns_empty(self, collector: RedditCollector) -> None:
        collector._client = AsyncMock()
        resp = _make_http_response({}, status_code=429)
        collector._client.get.return_value = resp

        posts = await collector._fetch_hot_posts("bitcoin")
        assert posts == []


class TestRedditCollectorAnalysis:
    def test_analyze_posts_bullish(self) -> None:
        c = RedditCollector()
        signal = c._analyze_posts(["moon bullish rally surge"], total_score=100, asset="BTC")
        assert signal.direction == Direction.BULLISH

    def test_analyze_posts_bearish(self) -> None:
        c = RedditCollector()
        signal = c._analyze_posts(["crash dump sell"], total_score=5, asset="BTC")
        assert signal.direction == Direction.BEARISH

    def test_analyze_posts_neutral(self) -> None:
        c = RedditCollector()
        signal = c._analyze_posts(["hello world"], total_score=10, asset="ETH")
        assert signal.direction == Direction.NEUTRAL
        assert signal.strength == 0.3

    def test_analyze_posts_mixed_keywords(self) -> None:
        c = RedditCollector()
        signal = c._analyze_posts(
            ["bullish moon rally", "crash dump"], total_score=50, asset="BTC"
        )
        # Equal count => neutral direction, strength 0.5
        assert signal.direction == Direction.NEUTRAL
        assert signal.strength == 0.5


class TestRedditCollectorHealthCheck:
    async def test_health_check_success(self) -> None:
        collector = RedditCollector()
        collector._client = AsyncMock()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        collector._client.get.return_value = resp

        assert await collector.health_check() is True

    async def test_health_check_http_error(self) -> None:
        collector = RedditCollector()
        collector._client = AsyncMock()
        collector._client.get.side_effect = httpx.HTTPError("fail")

        assert await collector.health_check() is False
