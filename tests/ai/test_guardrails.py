from ai.guardrails import clamp_confidence, clamp_score, safe_json_parse


def test_clamp_score_normal_range():
    assert clamp_score(0.5) == 0.5
    assert clamp_score(-0.3) == -0.3
    assert clamp_score(0.0) == 0.0


def test_clamp_score_out_of_range_high():
    assert clamp_score(2.5) == 1.0
    assert clamp_score(1.1) == 1.0


def test_clamp_score_out_of_range_low():
    assert clamp_score(-2.5) == -1.0
    assert clamp_score(-1.5) == -1.0


def test_clamp_score_custom_bounds():
    assert clamp_score(5.0, min_val=0.0, max_val=3.0) == 3.0
    assert clamp_score(-1.0, min_val=0.0, max_val=3.0) == 0.0


def test_clamp_confidence_normal():
    assert clamp_confidence(0.5) == 0.5
    assert clamp_confidence(0.0) == 0.0
    assert clamp_confidence(1.0) == 1.0


def test_clamp_confidence_out_of_range():
    assert clamp_confidence(1.5) == 1.0
    assert clamp_confidence(-0.3) == 0.0


def test_safe_json_parse_valid():
    result = safe_json_parse('{"score": 0.5, "confidence": 0.8}')
    assert result == {"score": 0.5, "confidence": 0.8}


def test_safe_json_parse_invalid():
    assert safe_json_parse("not json") is None
    assert safe_json_parse("{invalid}") is None


def test_safe_json_parse_empty_string():
    assert safe_json_parse("") is None
