"""Tests for rainbow.evaluation.context_enricher."""

from rainbow.evaluation.context_enricher import summarize_raw_data


class TestSummarizeRawData:
    def test_none_returns_default(self) -> None:
        assert summarize_raw_data(None) == "No technical data available."

    def test_empty_dict_returns_default(self) -> None:
        assert summarize_raw_data({}) == "No technical data available."

    def test_basic_dict(self) -> None:
        result = summarize_raw_data({"rsi": 55.0, "macd": 0.12})
        assert "rsi=55.0" in result
        assert "macd=0.12" in result

    def test_max_keys_respected(self) -> None:
        data = {f"k{i}": i for i in range(20)}
        result = summarize_raw_data(data, max_keys=3)
        parts = [p.strip() for p in result.split(",")]
        assert len(parts) == 3

    def test_custom_max_keys(self) -> None:
        data = {"a": 1, "b": 2, "c": 3, "d": 4}
        result = summarize_raw_data(data, max_keys=2)
        assert "a=1" in result
        assert "b=2" in result

    def test_preserves_string_values(self) -> None:
        result = summarize_raw_data({"trend": "up", "signal": "buy"})
        assert "trend=up" in result
        assert "signal=buy" in result
