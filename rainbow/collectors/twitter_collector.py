import logging

import httpx

from rainbow.collectors.base import BaseCollector
from rainbow.exceptions import CollectorError
from rainbow.models.signal import CryptoSignal, Direction, SignalType

log = logging.getLogger(__name__)

_BULLISH_KEYWORDS = frozenset({
    "bullish", "moon", "pump", "buy", "long", " breakout", "rally",
    "ath", "all-time high", "surge", "soar", "uptrend", "accumulation",
    "whale buy", "institutional", "adoption", "upgrade",
})

_BEARISH_KEYWORDS = frozenset({
    "bearish", "dump", "crash", "sell", "short", "breakdown",
    "capitulation", "bear", "bloodbath", "plunge", "scam",
    "rug pull", "hack", "exploit", "ban", "regulation", "sec",
})

_ASSET_QUERIES: dict[str, str] = {
    "BTC": "bitcoin OR btc",
    "ETH": "ethereum OR eth",
    "SOL": "solana OR sol",
}


class TwitterCollector(BaseCollector):
    def __init__(
        self,
        bearer_token: str = "",
        keywords: list[str] | None = None,
        assets: list[str] | None = None,
        max_results: int = 25,
    ):
        self._bearer_token = bearer_token
        self._keywords = keywords or ["bitcoin", "btc", "ethereum", "eth", "crypto"]
        self._assets = assets or ["BTC", "ETH"]
        self._max_results = max_results
        self._client = httpx.AsyncClient(
            base_url="https://api.twitter.com/2",
            headers={"Authorization": f"Bearer {bearer_token}"} if bearer_token else {},
            timeout=15.0,
        )

    @property
    def name(self) -> str:
        return "twitter"

    async def health_check(self) -> bool:
        if not self._bearer_token:
            return False
        try:
            resp = await self._client.get(
                "/tweets/search/recent",
                params={"query": "bitcoin", "max_results": 10},
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def collect(self) -> list[CryptoSignal]:
        if not self._bearer_token:
            return []

        signals: list[CryptoSignal] = []
        for asset in self._assets:
            try:
                tweets = await self._search_recent(asset)
                if not tweets:
                    continue
                signal = self._analyze_tweets(tweets, asset)
                if signal:
                    signals.append(signal)
            except httpx.HTTPError as exc:
                log.warning("Twitter API Fehler fuer %s: %s", asset, exc)
            except CollectorError:
                raise
            except Exception as exc:
                raise CollectorError(
                    self.name, f"Collection fehlgeschlagen fuer {asset}: {exc}"
                ) from exc

        return signals

    async def _search_recent(self, asset: str) -> list[dict]:
        query = _ASSET_QUERIES.get(asset, asset.lower())

        resp = await self._client.get(
            "/tweets/search/recent",
            params={
                "query": f"{query} -is:retweet lang:en",
                "max_results": str(min(self._max_results, 100)),
                "tweet.fields": "created_at,public_metrics",
            },
        )

        if resp.status_code == 401:
            raise CollectorError(
                self.name, "Twitter API: Unauthorized (Bearer Token ungueltig)"
            )
        if resp.status_code == 429:
            log.warning("Twitter API Rate Limit erreicht")
            return []

        resp.raise_for_status()
        return resp.json().get("data", [])

    def _analyze_tweets(self, tweets: list[dict], asset: str) -> CryptoSignal | None:
        if not tweets:
            return None

        bullish_count = 0
        bearish_count = 0
        total_engagement = 0

        for tweet in tweets:
            text = tweet.get("text", "").lower()
            metrics = tweet.get("public_metrics", {})
            engagement = metrics.get("like_count", 0) + metrics.get("retweet_count", 0)
            total_engagement += engagement

            if any(kw in text for kw in _BULLISH_KEYWORDS):
                bullish_count += 1
            if any(kw in text for kw in _BEARISH_KEYWORDS):
                bearish_count += 1

        total = bullish_count + bearish_count
        if total == 0:
            direction = Direction.NEUTRAL
            strength = 0.3
        elif bullish_count > bearish_count:
            direction = Direction.BULLISH
            strength = round(bullish_count / max(total, 1), 3)
        elif bearish_count > bullish_count:
            direction = Direction.BEARISH
            strength = round(bearish_count / max(total, 1), 3)
        else:
            direction = Direction.NEUTRAL
            strength = 0.5

        confidence = round(min(1.0, total / max(len(tweets), 1)), 3)

        return CryptoSignal(
            source=f"x_sentiment_{asset.lower()}",
            asset=asset,
            signal_type=SignalType.SOCIAL,
            direction=direction,
            strength=strength,
            confidence=confidence,
            value=float(bullish_count - bearish_count),
            raw_data={
                "bullish_count": bullish_count,
                "bearish_count": bearish_count,
                "total_tweets": len(tweets),
                "total_engagement": total_engagement,
            },
            metadata={"collector": "twitter", "query_window": "recent"},
        )

    async def close(self) -> None:
        await self._client.aclose()
