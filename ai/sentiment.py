from __future__ import annotations

import logging

import requests

import config
from ai.guardrails import safe_json_parse
from ai.providers import LLMProvider
from ai.providers import create_provider as _default_create_provider
from ai.validation import validate_sentiment_response

log = logging.getLogger(__name__)

# Kann von core/sentiment.py ueberschrieben werden fuer Patch-Kompatibilitaet.
create_provider = _default_create_provider

SENTIMENT_PROMPT = """Analyze the cryptocurrency market sentiment from these news headlines.
Return ONLY a JSON object:
{{"score": <float -1.0 to 1.0>, "confidence": <float 0.0 to 1.0>,
 "summary": "<brief summary>"}}
Negative score = bearish, positive = bullish, 0 = neutral.

News:
{news}"""


class SentimentAnalyzer:
    def __init__(self, api_key: str | None = None):
        self._llm: LLMProvider = create_provider(api_key=api_key)

    def analyze(self, headlines: list[str]) -> dict:
        if not headlines:
            return {"score": 0.0, "confidence": 0.0, "summary": "no data"}
        try:
            news_text = "\n".join(f"- {h}" for h in headlines)
            text = self._llm.complete(SENTIMENT_PROMPT.format(news=news_text), max_tokens=200)
            data = safe_json_parse(text)
            if data is None:
                raise ValueError("LLM-Response kein gueltiges JSON")
            return validate_sentiment_response(data)
        except Exception as e:
            log.warning(f"Sentiment-Analyse fehlgeschlagen, nutze neutral: {e}")
            return {"score": 0.0, "confidence": 0.0, "summary": "unavailable"}

    def fetch_headlines(self) -> list[str]:
        try:
            resp = requests.get(
                f"{config.CRYPTOCOMPARE_BASE}/news/?lang=EN&limit=10",
                timeout=10,
            )
            resp.raise_for_status()
            return [item["title"] for item in resp.json().get("Data", [])]
        except Exception as e:
            log.warning(f"News-Fetch fehlgeschlagen: {e}")
            return []
