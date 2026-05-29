from __future__ import annotations

from enum import Enum
from dataclasses import dataclass

from core.signal_model import Signal


class Severity(Enum):
    INFO = "info"
    WARN = "warn"
    BLOCK = "block"
    PANIC = "panic"

    def __lt__(self, other: Severity) -> bool:
        order = [Severity.INFO, Severity.WARN, Severity.BLOCK, Severity.PANIC]
        return order.index(self) < order.index(other)

    def __le__(self, other: Severity) -> bool:
        return self == other or self < other

    def __gt__(self, other: Severity) -> bool:
        return not self <= other

    def __ge__(self, other: Severity) -> bool:
        return not self < other


@dataclass
class PolicyResult:
    passed: bool
    severity: Severity
    reason: str
    policy_name: str


class Policy:
    """Base class for safety policies."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def check(self, signal: Signal, context: dict) -> PolicyResult:
        raise NotImplementedError
