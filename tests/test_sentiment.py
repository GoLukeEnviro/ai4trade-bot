# tests/test_sentiment.py
import json
from unittest.mock import MagicMock, patch

from core.sentiment import SentimentAnalyzer


def test_valid_llm_response():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps({"score": 0.7, "confidence": 0.85, "summary": "Bullish"})
    with patch("core.sentiment.create_provider", return_value=mock_llm):
        sa = SentimentAnalyzer(api_key="test-key")
        result = sa.analyze(["Bitcoin rallies past $70k"])
        assert result["score"] == 0.7
        assert result["confidence"] == 0.85
        assert result["summary"] == "Bullish"


def test_llm_exception_returns_neutral():
    mock_llm = MagicMock()
    mock_llm.complete.side_effect = Exception("API down")
    with patch("core.sentiment.create_provider", return_value=mock_llm):
        sa = SentimentAnalyzer(api_key="test-key")
        result = sa.analyze(["Bitcoin news"])
        assert result["score"] == 0.0
        assert result["confidence"] == 0.0
        assert result["summary"] == "unavailable"


def test_invalid_json_returns_neutral():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "not json at all"
    with patch("core.sentiment.create_provider", return_value=mock_llm):
        sa = SentimentAnalyzer(api_key="test-key")
        result = sa.analyze(["News"])
        assert result["score"] == 0.0
        assert result["confidence"] == 0.0


def test_out_of_range_values_are_clamped():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps({"score": 2.5, "confidence": 5.0, "summary": "extreme"})
    with patch("core.sentiment.create_provider", return_value=mock_llm):
        sa = SentimentAnalyzer(api_key="test-key")
        result = sa.analyze(["News"])
        assert result["score"] == 1.0
        assert result["confidence"] == 1.0


def test_negative_out_of_range_clamped():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps({"score": -3.0, "confidence": -1.0, "summary": "extreme negative"})
    with patch("core.sentiment.create_provider", return_value=mock_llm):
        sa = SentimentAnalyzer(api_key="test-key")
        result = sa.analyze(["News"])
        assert result["score"] == -1.0
        assert result["confidence"] == 0.0


def test_empty_headlines_list():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps({"score": 0.7, "confidence": 0.85, "summary": "Bullish"})
    with patch("core.sentiment.create_provider", return_value=mock_llm):
        sa = SentimentAnalyzer(api_key="test-key")
        result = sa.analyze([])
        assert result["score"] == 0.0
        assert result["confidence"] == 0.0
