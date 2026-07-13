"""Rolling signal-performance metrics and CUSUM drift detection."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class SignalPerformanceWindow:
    """Rolling window over the latest signal outcomes."""

    window_size: int = 50
    outcomes: deque[str] = field(init=False)
    confidences: deque[float] = field(init=False)

    def __post_init__(self) -> None:
        self.outcomes = deque(maxlen=self.window_size)
        self.confidences = deque(maxlen=self.window_size)

    def record(self, outcome: str, predicted_confidence: float) -> None:
        self.outcomes.append(outcome)
        self.confidences.append(predicted_confidence)

    @property
    def win_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(1 for outcome in self.outcomes if outcome == "win") / len(self.outcomes)

    @property
    def sample_size(self) -> int:
        return len(self.outcomes)

    @property
    def confidence_calibration_error(self) -> float:
        if not self.confidences:
            return 0.0
        return abs(sum(self.confidences) / len(self.confidences) - self.win_rate)


class ModelDriftDetector:
    """CUSUM Page-Hinkley detector for negative win-rate drift."""

    def __init__(self, baseline_win_rate: float = 0.55, threshold: float = 0.10) -> None:
        self.baseline = baseline_win_rate
        self.threshold = threshold
        self.cusum_pos = 0.0
        self.cusum_neg = 0.0
        self.alarm_active = False

    def update(self, outcome: str) -> bool:
        """Return True when the drift alarm is active after this outcome."""
        result = 1.0 if outcome == "win" else 0.0
        deviation = result - self.baseline
        self.cusum_pos = max(0.0, self.cusum_pos + deviation)
        self.cusum_neg = max(0.0, self.cusum_neg - deviation)
        self.alarm_active = self.cusum_neg >= self.threshold
        return self.alarm_active

    def reset(self) -> None:
        self.cusum_pos = 0.0
        self.cusum_neg = 0.0
        self.alarm_active = False
