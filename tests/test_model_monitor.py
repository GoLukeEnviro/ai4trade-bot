import pytest

from monitoring.model_monitor import ModelDriftDetector, SignalPerformanceWindow


def test_40_wins_10_losses_win_rate_no_drift_alarm():
    window = SignalPerformanceWindow()
    detector = ModelDriftDetector(threshold=30.0)
    for outcome in ["win"] * 40 + ["loss"] * 10:
        window.record(outcome, 0.8)
        detector.update(outcome)
    assert window.win_rate == 0.80
    assert detector.alarm_active is False


def test_20_wins_30_losses_win_rate_drift_alarm():
    window = SignalPerformanceWindow()
    detector = ModelDriftDetector(threshold=10.0)
    for outcome in ["win"] * 20 + ["loss"] * 30:
        window.record(outcome, 0.4)
        detector.update(outcome)
    assert window.win_rate == 0.40
    assert detector.alarm_active is True


def test_empty_window_defaults():
    window = SignalPerformanceWindow()
    detector = ModelDriftDetector()
    assert window.win_rate == 0.0
    assert detector.alarm_active is False


def test_cusum_reset_clears_negative_drift():
    detector = ModelDriftDetector()
    detector.update("loss")
    detector.reset()
    assert detector.cusum_neg == 0.0
    assert detector.alarm_active is False


def test_calibration_error_perfect_calibration():
    window = SignalPerformanceWindow()
    for outcome in ["win", "loss"]:
        window.record(outcome, 0.5)
    assert window.confidence_calibration_error == pytest.approx(0.0)
