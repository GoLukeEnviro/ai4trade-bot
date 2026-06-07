import pytest

from rainbow.collectors.reddit_collector import RedditCollector
from rainbow.collectors.twitter_collector import TwitterCollector
from rainbow.models.signal import Direction, SignalType


class TestTwitterCollector:
    @pytest.fixture
    def collector(self):
        return TwitterCollector(bearer_token="test-token", assets=["BTC"])

    def test_name(self, collector):
        assert collector.name == "twitter"

    @pytest.mark.anyio
    async def test_collect_without_token_returns_empty(self):
        col = TwitterCollector(bearer_token="", assets=["BTC"])
        signals = await col.collect()
        assert signals == []

    def test_analyze_bullish_tweets(self, collector):
        tweets = [
            {"text": "Bitcoin is extremely bullish right now! Time to buy!",
             "public_metrics": {"like_count": 50, "retweet_count": 10}},
            {"text": "BTC rally incoming, accumulation phase",
             "public_metrics": {"like_count": 30, "retweet_count": 5}},
            {"text": "Just another day in crypto", "public_metrics": {"like_count": 5, "retweet_count": 1}},
        ]
        signal = collector._analyze_tweets(tweets, "BTC")
        assert signal is not None
        assert signal.asset == "BTC"
        assert signal.signal_type == SignalType.SOCIAL
        assert signal.direction == Direction.BULLISH
        assert signal.strength > 0.0
        assert signal.source == "x_sentiment_btc"
        assert signal.raw_data["bullish_count"] > 0

    def test_analyze_bearish_tweets(self, collector):
        tweets = [
            {"text": "Bitcoin crash incoming, time to sell everything",
             "public_metrics": {"like_count": 20, "retweet_count": 3}},
            {"text": "Market dump, bearish signals everywhere",
             "public_metrics": {"like_count": 15, "retweet_count": 2}},
        ]
        signal = collector._analyze_tweets(tweets, "BTC")
        assert signal is not None
        assert signal.direction == Direction.BEARISH

    def test_analyze_neutral_tweets(self, collector):
        tweets = [
            {"text": "Bitcoin price is at 50000", "public_metrics": {"like_count": 1, "retweet_count": 0}},
        ]
        signal = collector._analyze_tweets(tweets, "BTC")
        assert signal is not None
        assert signal.direction == Direction.NEUTRAL
        assert signal.strength == 0.3

    def test_analyze_empty_tweets(self, collector):
        signal = collector._analyze_tweets([], "BTC")
        assert signal is None

    @pytest.mark.anyio
    async def test_health_check_no_token(self):
        col = TwitterCollector(bearer_token="")
        assert await col.health_check() is False


class TestRedditCollector:
    @pytest.fixture
    def collector(self):
        return RedditCollector(assets=["BTC"])

    def test_name(self, collector):
        assert collector.name == "reddit"

    def test_analyze_bullish_posts(self, collector):
        titles = [
            "Bitcoin bullish breakout imminent!",
            "BTC accumulation phase, buy now",
            "All-time high incoming for Bitcoin",
        ]
        signal = collector._analyze_posts(titles, total_score=500, asset="BTC")
        assert signal.asset == "BTC"
        assert signal.signal_type == SignalType.SOCIAL
        assert signal.direction == Direction.BULLISH
        assert signal.source == "reddit_btc"
        assert signal.raw_data["bullish_count"] == 3

    def test_analyze_bearish_posts(self, collector):
        titles = [
            "Bitcoin crash, sell everything",
            "BTC dump incoming, capitulation mode",
            "Market bloodbath today",
        ]
        signal = collector._analyze_posts(titles, total_score=200, asset="BTC")
        assert signal.direction == Direction.BEARISH

    def test_analyze_mixed_posts(self, collector):
        titles = [
            "Bitcoin bullish breakout!",
            "BTC crash incoming",
            "Just another day in crypto",
        ]
        signal = collector._analyze_posts(titles, total_score=100, asset="BTC")
        assert signal is not None
        assert signal.direction in (Direction.BULLISH, Direction.BEARISH, Direction.NEUTRAL)

    def test_analyze_neutral_posts(self, collector):
        titles = ["What do you think about Bitcoin?", "Bitcoin price discussion"]
        signal = collector._analyze_posts(titles, total_score=50, asset="BTC")
        assert signal.direction == Direction.NEUTRAL

    def test_custom_subreddits(self):
        col = RedditCollector(
            assets=["SOL"],
            subreddits={"SOL": ["solana", "cryptocurrency"]},
        )
        assert col.name == "reddit"

    @pytest.mark.anyio
    async def test_collect_with_mocked_api(self, collector):
        from unittest.mock import AsyncMock, patch

        mock_response = type("Response", (), {
            "status_code": 200,
            "json": lambda self: {
                "data": {
                    "children": [
                        {"data": {"title": "Bitcoin bullish rally!", "score": 100}},
                        {"data": {"title": "BTC crash incoming", "score": 50}},
                    ]
                }
            },
            "raise_for_status": lambda self: None,
        })()

        with patch.object(collector._client, "get", new_callable=AsyncMock, return_value=mock_response):
            signals = await collector.collect()
            assert len(signals) == 1
            assert signals[0].asset == "BTC"
            assert signals[0].signal_type == SignalType.SOCIAL
