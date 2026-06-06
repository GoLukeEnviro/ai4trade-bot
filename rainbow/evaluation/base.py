from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rainbow.evaluation.models import AIEvaluation
    from rainbow.models.signal import CryptoSignal


class BaseEvaluator(ABC):
    @abstractmethod
    async def evaluate(self, signal: CryptoSignal) -> AIEvaluation | None: ...
