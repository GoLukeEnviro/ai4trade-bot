from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from rainbow.collectors.news_collector import NewsCollector
from rainbow.distribution.webhooks import WebhookManager, WebhookSubscription
from rainbow.models.signal import CryptoSignal, Direction, SignalType
from rainbow.processor.scorer import RainbowScorer


class TestNewsCollector:
    @pytest.fixture
    def collector(self):
        return NewsCollector(assets=["BTC", "ETH"])

    def test_name(self, collector):
        assert collector.name == "news"

    def test_filter_btc_articles(self, collector):
        articles = [
            {"title": "Bitcoin price surges to new highs", "body": "BTC rally continues", "categories": "BTC|Trading"},
            {"title": "Ethereum upgrade announced", "body": "ETH 2.0 progress", "categories": "ETH"},
            {"title": "Stock market update", "body": "SPX drops", "categories": "Stocks"},
        ]
        btc = collector._filter_for_asset(articles, "BTC")
        assert len(btc) == 1
        assert "Bitcoin" in btc[0]["title"]

    def test_filter_eth_articles(self, collector):
        articles = [
            {"title": "Ethereum DeFi growth", "body": "ETH ecosystem", "categories": "ETH"},
            {"title": "Bitcoin crash", "body": "BTC dump", "categories": "BTC"},
        ]
        eth = collector._filter_for_asset(articles, "ETH")
        assert len(eth) == 1

    def test_analyze_bullish_news(self, collector):
        articles = [
            {"title": "Bitcoin bullish breakout confirmed",
             "body": "Institutional adoption surging", "categories": "BTC"},
            {"title": "BTC rally to all-time high", "body": "Partnership announced", "categories": "BTC"},
        ]
        signal = collector._analyze_articles(articles, "BTC")
        assert signal is not None
        assert signal.asset == "BTC"
        assert signal.signal_type == SignalType.NEWS
        assert signal.direction == Direction.BULLISH
        assert signal.source == "news_btc"
        assert signal.raw_data["bullish_count"] >= 2

    def test_analyze_bearish_news(self, collector):
        articles = [
            {"title": "Bitcoin crash after SEC regulation", "body": "Ban concerns grow", "categories": "BTC"},
            {"title": "BTC exploit discovered", "body": "Hack risk warning", "categories": "BTC"},
        ]
        signal = collector._analyze_articles(articles, "BTC")
        assert signal is not None
        assert signal.direction == Direction.BEARISH

    def test_analyze_empty_articles(self, collector):
        assert collector._analyze_articles([], "BTC") is None

    @pytest.mark.anyio
    async def test_collect_with_mocked_api(self, collector):
        mock_response = type("Response", (), {
            "status_code": 200,
            "json": lambda self: {
                "Data": [
                    {"title": "Bitcoin bullish rally", "body": "BTC adoption surges", "categories": "BTC"},
                    {"title": "Bitcoin crash warning", "body": "SEC regulation risk", "categories": "BTC"},
                ]
            },
            "raise_for_status": lambda self: None,
        })()

        with patch.object(collector._client, "get", new_callable=AsyncMock, return_value=mock_response):
            signals = await collector.collect()
            assert len(signals) >= 1
            assert any(s.asset == "BTC" for s in signals)

    @pytest.mark.anyio
    async def test_collect_timeout_returns_empty(self, collector):
        import httpx
        with patch.object(
            collector._client, "get",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("timeout"),
        ):
            signals = await collector.collect()
            assert signals == []


class TestWebhookManager:
    @pytest.fixture
    def manager(self):
        return WebhookManager()

    def test_subscribe(self, manager):
        sub = WebhookSubscription(url="https://example.com/hook")
        sub_id = manager.subscribe(sub)
        assert sub_id.startswith("wh_")
        assert len(manager.list_subscriptions()) == 1

    def test_unsubscribe(self, manager):
        sub = WebhookSubscription(url="https://example.com/hook")
        sub_id = manager.subscribe(sub)
        assert manager.unsubscribe(sub_id) is True
        assert manager.unsubscribe("nonexistent") is False

    def test_subscription_matches_asset(self):
        sub = WebhookSubscription(url="https://example.com/hook", asset="BTC")
        btc_signal = CryptoSignal(
            source="ta", asset="BTC", signal_type=SignalType.TECHNICAL,
            strength=0.8, confidence=0.7,
        )
        eth_signal = CryptoSignal(
            source="ta", asset="ETH", signal_type=SignalType.TECHNICAL,
            strength=0.8, confidence=0.7,
        )
        assert sub.matches(btc_signal) is True
        assert sub.matches(eth_signal) is False

    def test_subscription_matches_source(self):
        sub = WebhookSubscription(url="https://example.com/hook", source="ta_1h")
        matching = CryptoSignal(
            source="ta_1h", asset="BTC", signal_type=SignalType.TECHNICAL,
            strength=0.5, confidence=0.5,
        )
        non_matching = CryptoSignal(
            source="x_sentiment", asset="BTC", signal_type=SignalType.SOCIAL,
            strength=0.5, confidence=0.5,
        )
        assert sub.matches(matching) is True
        assert sub.matches(non_matching) is False

    def test_subscription_no_filters_matches_all(self):
        sub = WebhookSubscription(url="https://example.com/hook")
        sig = CryptoSignal(
            source="anything", asset="SOL", signal_type=SignalType.NEWS,
            strength=0.5, confidence=0.5,
        )
        assert sub.matches(sig) is True

    @pytest.mark.anyio
    async def test_dispatch_calls_matching_subscriptions(self, manager):
        sub = WebhookSubscription(url="https://example.com/hook", asset="BTC")
        manager.subscribe(sub)

        signal = CryptoSignal(
            source="ta", asset="BTC", signal_type=SignalType.TECHNICAL,
            direction=Direction.BULLISH, strength=0.8, confidence=0.7,
        )

        with patch.object(manager._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = type("Response", (), {"status_code": 200})()
            await manager.dispatch(signal)
            mock_post.assert_called_once()


class TestEnhancedScorer:
    def test_temporal_decay_old_signals_weighted_less(self):
        scorer = RainbowScorer(
            decay_threshold_seconds=60,
            decay_factor=0.5,
            cross_signal_boost=1.0,
            weights={"technical": 0.5, "social": 0.5},
        )

        now = datetime.now(UTC)

        # Frisch + alt gemischt: das alte Signal ist stark (0.9), wird aber durch Decay entwertet
        mixed_signals = [
            CryptoSignal(
                source="ta", asset="BTC", signal_type=SignalType.TECHNICAL,
                direction=Direction.BULLISH, strength=0.5, confidence=0.8,
                timestamp=now,
            ),
            CryptoSignal(
                source="x", asset="BTC", signal_type=SignalType.SOCIAL,
                direction=Direction.BULLISH, strength=0.9, confidence=0.8,
                timestamp=now - timedelta(hours=5),
            ),
        ]
        all_fresh = [
            CryptoSignal(
                source="ta", asset="BTC", signal_type=SignalType.TECHNICAL,
                direction=Direction.BULLISH, strength=0.5, confidence=0.8,
                timestamp=now,
            ),
            CryptoSignal(
                source="x", asset="BTC", signal_type=SignalType.SOCIAL,
                direction=Direction.BULLISH, strength=0.9, confidence=0.8,
                timestamp=now,
            ),
        ]

        scored_mixed = scorer.score(mixed_signals)
        scored_fresh = scorer.score(all_fresh)

        assert scored_mixed[0].rainbow_score is not None
        assert scored_fresh[0].rainbow_score is not None
        # Alle frisch → starkes Social-Signal zaehlt voll → hoeherer gewichteter Score
        assert scored_fresh[0].rainbow_score > scored_mixed[0].rainbow_score

    def test_cross_signal_confirmation_boost(self):
        scorer = RainbowScorer(cross_signal_boost=1.5)

        confirmed = [
            CryptoSignal(
                source="ta", asset="BTC", signal_type=SignalType.TECHNICAL,
                direction=Direction.BULLISH, strength=0.8, confidence=0.7,
            ),
            CryptoSignal(
                source="x", asset="BTC", signal_type=SignalType.SOCIAL,
                direction=Direction.BULLISH, strength=0.7, confidence=0.6,
            ),
        ]
        unconfirmed = [
            CryptoSignal(
                source="ta", asset="BTC", signal_type=SignalType.TECHNICAL,
                direction=Direction.BULLISH, strength=0.8, confidence=0.7,
            ),
            CryptoSignal(
                source="x", asset="BTC", signal_type=SignalType.SOCIAL,
                direction=Direction.BEARISH, strength=0.7, confidence=0.6,
            ),
        ]

        scored_confirmed = scorer.score(confirmed)
        scored_unconfirmed = scorer.score(unconfirmed)

        assert scored_confirmed[0].rainbow_score > scored_unconfirmed[0].rainbow_score

    def test_backward_compatible_simple_scoring(self):
        scorer = RainbowScorer()
        signals = [
            CryptoSignal(
                source="ta", asset="BTC", signal_type=SignalType.TECHNICAL,
                direction=Direction.BULLISH, strength=0.9, confidence=0.8,
            ),
        ]
        scored = scorer.score(signals)
        assert len(scored) == 1
        assert scored[0].rainbow_score is not None
        assert 0.0 <= scored[0].rainbow_score <= 1.0

    def test_empty_signals_returns_empty(self):
        scorer = RainbowScorer()
        assert scorer.score([]) == []
