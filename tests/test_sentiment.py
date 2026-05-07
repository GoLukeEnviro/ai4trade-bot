# tests/test_sentiment.py
import json
from unittest.mock import MagicMock, patch
from core.sentiment import SentimentAnalyzer


def _mock_claude_response(score=0.7, confidence=0.85, summary="Bullish"):
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(type="text", text=json.dumps({
        "score": score,
        "confidence": confidence,
        "summary": summary,
    }))]
    return mock_resp


def test_valid_claude_response():
    with patch("core.sentiment.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_claude_response()
        sa = SentimentAnalyzer(api_key="test-key")
        result = sa.analyze(["Bitcoin rallies past $70k"])
        assert result["score"] == 0.7
        assert result["confidence"] == 0.85
        assert result["summary"] == "Bullish"


def test_claude_exception_returns_neutral():
    with patch("core.sentiment.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = Exception("API down")
        sa = SentimentAnalyzer(api_key="test-key")
        result = sa.analyze(["Bitcoin news"])
        assert result["score"] == 0.0
        assert result["confidence"] == 0.0
        assert result["summary"] == "unavailable"


def test_invalid_json_returns_neutral():
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(type="text", text="not json at all")]
    with patch("core.sentiment.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_resp
        sa = SentimentAnalyzer(api_key="test-key")
        result = sa.analyze(["News"])
        assert result["score"] == 0.0
        assert result["confidence"] == 0.0


def test_out_of_range_values_are_clamped():
    with patch("core.sentiment.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_claude_response(
            score=2.5, confidence=5.0, summary="extreme"
        )
        sa = SentimentAnalyzer(api_key="test-key")
        result = sa.analyze(["News"])
        assert result["score"] == 1.0
        assert result["confidence"] == 1.0


def test_negative_out_of_range_clamped():
    with patch("core.sentiment.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_claude_response(
            score=-3.0, confidence=-1.0, summary="extreme negative"
        )
        sa = SentimentAnalyzer(api_key="test-key")
        result = sa.analyze(["News"])
        assert result["score"] == -1.0
        assert result["confidence"] == 0.0


def test_empty_headlines_list():
    with patch("core.sentiment.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_claude_response()
        sa = SentimentAnalyzer(api_key="test-key")
        result = sa.analyze([])
        assert result["score"] == 0.0
        assert result["confidence"] == 0.0
