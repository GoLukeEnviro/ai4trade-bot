import logging

import httpx

from rainbow.collectors.base import BaseCollector
from rainbow.exceptions import CollectorError
from rainbow.models.signal import CryptoSignal, Direction, SignalType

log = logging.getLogger(__name__)

_BULLISH_KEYWORDS = frozenset({
    "bullish", "rally", "surge", "soar", "breakout", "ath",
    "all-time high", "adoption", "upgrade", "partnership",
    "institutional", "etf approved", "positive", "growth",
    "milestone", "launch",
})

_BEARISH_KEYWORDS = frozenset({
    "bearish", "crash", "dump", "plunge", "decline", "ban",
    "hack", "exploit", "sec", "regulation", "lawsuit",
    "fraud", "scam", "rug pull", "capitulation", "warning",
    "risk", "concern", "negative", "sanctions",
})

_ASSET_KEYWORDS: dict[str, list[str]] = {
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "eth"],
    "SOL": ["solana", "sol"],
}


class NewsCollector(BaseCollector):
    """Sammelt Crypto-News von CryptoCompare und generiert Sentiment-Signale."""

    def __init__(
        self,
        assets: list[str] | None = None,
        cryptocompare_base: str = "https://min-api.cryptocompare.com/data/v2",
        rss_feeds: list[str] | None = None,
        max_articles: int = 20,
    ):
        self._assets = assets or ["BTC", "ETH", "SOL"]
        self._cryptocompare_base = cryptocompare_base
        self._rss_feeds = rss_feeds or []
        self._max_articles = max_articles
        self._client = httpx.AsyncClient(timeout=15.0)

    @property
    def name(self) -> str:
        return "news"

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(
                f"{self._cryptocompare_base}/news/",
                params={"lang": "EN", "limit": "1"},
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def collect(self) -> list[CryptoSignal]:
        signals: list[CryptoSignal] = []
        articles = await self._fetch_cryptocompare()
        if not articles:
            return signals

        for asset in self._assets:
            relevant = self._filter_for_asset(articles, asset)
            if not relevant:
                continue
            signal = self._analyze_articles(relevant, asset)
            if signal:
                signals.append(signal)

        return signals

    async def _fetch_cryptocompare(self) -> list[dict]:
        try:
            resp = await self._client.get(
                f"{self._cryptocompare_base}/news/",
                params={"lang": "EN", "limit": str(self._max_articles)},
            )
            resp.raise_for_status()
            return resp.json().get("Data", [])
        except httpx.TimeoutException:
            log.warning("CryptoCompare News Timeout")
            return []
        except httpx.HTTPStatusError as exc:
            log.warning("CryptoCompare News HTTP %d", exc.response.status_code)
            return []
        except httpx.RequestError as exc:
            raise CollectorError(self.name, f"Netzwerkfehler: {exc}") from exc

    def _filter_for_asset(self, articles: list[dict], asset: str) -> list[dict]:
        keywords = _ASSET_KEYWORDS.get(asset, [asset.lower()])
        relevant = []
        for art in articles:
            text = f"{art.get('title', '')} {art.get('body', '')}".lower()
            if any(kw in text for kw in keywords):
                relevant.append(art)
        return relevant

    def _analyze_articles(self, articles: list[dict], asset: str) -> CryptoSignal | None:
        if not articles:
            return None

        bullish = 0
        bearish = 0
        categories: set[str] = set()

        for art in articles:
            text = f"{art.get('title', '')} {art.get('body', '')}".lower()
            if any(kw in text for kw in _BULLISH_KEYWORDS):
                bullish += 1
            if any(kw in text for kw in _BEARISH_KEYWORDS):
                bearish += 1
            for cat in art.get("categories", "").split("|"):
                if cat.strip():
                    categories.add(cat.strip())

        total = bullish + bearish
        if total == 0:
            direction = Direction.NEUTRAL
            strength = 0.3
        elif bullish > bearish:
            direction = Direction.BULLISH
            strength = round(bullish / max(total, 1), 3)
        elif bearish > bullish:
            direction = Direction.BEARISH
            strength = round(bearish / max(total, 1), 3)
        else:
            direction = Direction.NEUTRAL
            strength = 0.5

        confidence = round(min(1.0, total / max(len(articles), 1)), 3)

        return CryptoSignal(
            source=f"news_{asset.lower()}",
            asset=asset,
            signal_type=SignalType.NEWS,
            direction=direction,
            strength=strength,
            confidence=confidence,
            value=float(bullish - bearish),
            raw_data={
                "bullish_count": bullish,
                "bearish_count": bearish,
                "total_articles": len(articles),
                "categories": sorted(categories)[:10],
            },
            metadata={"collector": "news", "provider": "cryptocompare"},
        )

    async def close(self) -> None:
        await self._client.aclose()
