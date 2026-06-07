from __future__ import annotations

import logging

import httpx

from rainbow.collectors.base import BaseCollector
from rainbow.exceptions import CollectorError
from rainbow.models.signal import CryptoSignal, Direction, SignalType

log = logging.getLogger(__name__)

_BULLISH_KEYWORDS = frozenset(
    {
        "bullish",
        "moon",
        "pump",
        "buy",
        "long",
        "breakout",
        "rally",
        "ath",
        "all-time high",
        "surge",
        "soar",
        "uptrend",
        "accumulation",
    }
)

_BEARISH_KEYWORDS = frozenset(
    {
        "bearish",
        "dump",
        "crash",
        "sell",
        "short",
        "breakdown",
        "capitulation",
        "bear",
        "bloodbath",
        "plunge",
        "scam",
        "rug pull",
        "hack",
        "exploit",
        "ban",
        "regulation",
    }
)

_DEFAULT_SUBREDDITS: dict[str, list[str]] = {
    "BTC": ["bitcoin", "btc", "cryptocurrency"],
    "ETH": ["ethereum", "ethtrader", "cryptocurrency"],
    "SOL": ["solana", "cryptocurrency"],
}

_REDDIT_API_URL = "https://www.reddit.com"
_USER_AGENT = "RainbowIntelligenceEngine/0.1.0"


class RedditCollector(BaseCollector):
    def __init__(
        self,
        assets: list[str] | None = None,
        subreddits: dict[str, list[str]] | None = None,
        posts_per_subreddit: int = 15,
    ):
        self._assets = assets or ["BTC", "ETH", "SOL"]
        self._subreddits = subreddits or _DEFAULT_SUBREDDITS
        self._posts_per_subreddit = posts_per_subreddit
        self._client = httpx.AsyncClient(
            base_url=_REDDIT_API_URL,
            headers={"User-Agent": _USER_AGENT},
            timeout=15.0,
        )

    @property
    def name(self) -> str:
        return "reddit"

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/r/bitcoin/hot.json", params={"limit": 1})
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def collect(self) -> list[CryptoSignal]:
        signals: list[CryptoSignal] = []
        for asset in self._assets:
            subs = self._subreddits.get(asset, ["cryptocurrency"])
            try:
                signal = await self._collect_for_asset(asset, subs)
                if signal:
                    signals.append(signal)
            except httpx.HTTPError as exc:
                log.warning("Reddit API Fehler fuer %s: %s", asset, exc)
            except Exception as exc:
                raise CollectorError(self.name, f"Collection fehlgeschlagen fuer {asset}: {exc}") from exc
        return signals

    async def _collect_for_asset(self, asset: str, subreddits: list[str]) -> CryptoSignal | None:
        all_titles: list[str] = []
        total_score = 0

        for sub in subreddits:
            try:
                posts = await self._fetch_hot_posts(sub)
                for post in posts:
                    title = post.get("data", {}).get("title", "")
                    score = post.get("data", {}).get("score", 0)
                    all_titles.append(title)
                    total_score += score
            except httpx.HTTPError as exc:
                log.warning("Reddit r/%s Fehler: %s", sub, exc)

        if not all_titles:
            return None

        return self._analyze_posts(all_titles, total_score, asset)

    async def _fetch_hot_posts(self, subreddit: str) -> list[dict]:
        resp = await self._client.get(
            f"/r/{subreddit}/hot.json",
            params={"limit": str(self._posts_per_subreddit)},
        )

        if resp.status_code == 429:
            log.warning("Reddit Rate Limit erreicht fuer r/%s", subreddit)
            return []

        resp.raise_for_status()
        return resp.json().get("data", {}).get("children", [])

    def _analyze_posts(self, titles: list[str], total_score: int, asset: str) -> CryptoSignal:
        bullish = 0
        bearish = 0

        for title in titles:
            lower = title.lower()
            if any(kw in lower for kw in _BULLISH_KEYWORDS):
                bullish += 1
            if any(kw in lower for kw in _BEARISH_KEYWORDS):
                bearish += 1

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

        confidence = round(min(1.0, total / max(len(titles), 1)), 3)

        return CryptoSignal(
            source=f"reddit_{asset.lower()}",
            asset=asset,
            signal_type=SignalType.SOCIAL,
            direction=direction,
            strength=strength,
            confidence=confidence,
            value=float(bullish - bearish),
            raw_data={
                "bullish_count": bullish,
                "bearish_count": bearish,
                "total_posts": len(titles),
                "total_upvotes": total_score,
            },
            metadata={"collector": "reddit"},
        )

    async def close(self) -> None:
        await self._client.aclose()
