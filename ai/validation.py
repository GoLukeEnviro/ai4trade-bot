from ai.guardrails import clamp_confidence, clamp_score


def validate_sentiment_response(data: dict) -> dict:
    """
    Sentiment-Response validieren und normalisieren.
    Garantiert: score in [-1, 1], confidence in [0, 1], summary immer str.
    """
    try:
        score = clamp_score(float(data.get("score", 0.0)))
    except (ValueError, TypeError):
        score = 0.0
    try:
        confidence = clamp_confidence(float(data.get("confidence", 0.0)))
    except (ValueError, TypeError):
        confidence = 0.0
    summary = str(data.get("summary", ""))
    return {"score": score, "confidence": confidence, "summary": summary}
