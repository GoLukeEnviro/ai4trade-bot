from ai.validation import validate_sentiment_response


def test_validate_sentiment_valid_data():
    data = {"score": 0.6, "confidence": 0.85, "summary": "bullish trend"}
    result = validate_sentiment_response(data)
    assert result["score"] == 0.6
    assert result["confidence"] == 0.85
    assert result["summary"] == "bullish trend"


def test_validate_sentiment_missing_fields():
    result = validate_sentiment_response({})
    assert result["score"] == 0.0
    assert result["confidence"] == 0.0
    assert result["summary"] == ""


def test_validate_sentiment_extreme_values_clamped():
    data = {"score": 5.0, "confidence": 2.0, "summary": "extreme"}
    result = validate_sentiment_response(data)
    assert result["score"] == 1.0
    assert result["confidence"] == 1.0


def test_validate_sentiment_negative_extreme_clamped():
    data = {"score": -3.0, "confidence": -0.5}
    result = validate_sentiment_response(data)
    assert result["score"] == -1.0
    assert result["confidence"] == 0.0


def test_validate_sentiment_non_numeric_handled():
    data = {"score": "high", "confidence": "maybe", "summary": 123}
    result = validate_sentiment_response(data)
    assert isinstance(result["score"], float)
    assert isinstance(result["confidence"], float)
    assert isinstance(result["summary"], str)
