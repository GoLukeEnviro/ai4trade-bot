"""Tests for rainbow.evaluation.cache — EvaluationCache."""



from rainbow.evaluation.cache import EvaluationCache
from rainbow.evaluation.models import AIEvaluation


def _make_evaluation(ai_confidence: float = 0.8) -> AIEvaluation:
    return AIEvaluation(
        ai_confidence=ai_confidence,
        risk_level="medium",
        market_regime="trending",
        reasoning="test",
        model_used="test-model",
        evaluation_latency_ms=10,
    )


class TestEvaluationCacheConstruction:
    def test_default_construction(self) -> None:
        cache = EvaluationCache()
        assert cache._ttl == 300
        assert cache._max_size == 500

    def test_custom_construction(self) -> None:
        cache = EvaluationCache(ttl_seconds=60, max_size=100)
        assert cache._ttl == 60
        assert cache._max_size == 100


class TestEvaluationCacheGetSet:
    async def test_set_and_get(self) -> None:
        cache = EvaluationCache()
        evaluation = _make_evaluation()
        await cache.set("BTC", "bullish", evaluation)
        result = await cache.get("BTC", "bullish")
        assert result is not None
        assert result.ai_confidence == 0.8

    async def test_get_missing_key(self) -> None:
        cache = EvaluationCache()
        result = await cache.get("BTC", "bullish")
        assert result is None

    async def test_overwrite_existing_key(self) -> None:
        cache = EvaluationCache()
        eval1 = _make_evaluation(ai_confidence=0.5)
        eval2 = _make_evaluation(ai_confidence=0.9)
        await cache.set("BTC", "bullish", eval1)
        await cache.set("BTC", "bullish", eval2)
        result = await cache.get("BTC", "bullish")
        assert result is not None
        assert result.ai_confidence == 0.9


class TestEvaluationCacheTTL:
    async def test_expired_entry_returns_none(self) -> None:
        cache = EvaluationCache(ttl_seconds=0)
        evaluation = _make_evaluation()
        # TTL=0 means entries expire immediately
        await cache.set("BTC", "bullish", evaluation)
        result = await cache.get("BTC", "bullish")
        assert result is None


class TestEvaluationCacheEviction:
    async def test_max_size_eviction(self) -> None:
        cache = EvaluationCache(ttl_seconds=600, max_size=3)
        for i in range(5):
            await cache.set(f"ASSET{i}", "bullish", _make_evaluation(ai_confidence=0.1 * i))

        # Only last 3 entries should remain
        result0 = await cache.get("ASSET0", "bullish")
        result4 = await cache.get("ASSET4", "bullish")
        assert result0 is None
        assert result4 is not None


class TestEvaluationCacheKeyFormat:
    async def test_key_format(self) -> None:
        cache = EvaluationCache()
        key = cache._make_key("ETH", "bearish")
        assert key == "ETH:bearish"

    async def test_different_directions_stored_separately(self) -> None:
        cache = EvaluationCache()
        eval_bull = _make_evaluation(ai_confidence=0.9)
        eval_bear = _make_evaluation(ai_confidence=0.2)
        await cache.set("BTC", "bullish", eval_bull)
        await cache.set("BTC", "bearish", eval_bear)
        result_bull = await cache.get("BTC", "bullish")
        result_bear = await cache.get("BTC", "bearish")
        assert result_bull is not None and result_bull.ai_confidence == 0.9
        assert result_bear is not None and result_bear.ai_confidence == 0.2
