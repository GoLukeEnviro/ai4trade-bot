from abc import ABC, abstractmethod

from rainbow.models.signal import CryptoSignal


class BaseCollector(ABC):
    """Jeder Collector erbt hiervon. collect() MUSS list[CryptoSignal] zurueckgeben."""

    @abstractmethod
    async def collect(self) -> list[CryptoSignal]:
        """Sammle Daten und gib eine Liste von CryptoSignal zurueck."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Eindeutiger Name des Collectors (z.B. 'ta', 'twitter')."""
        ...

    async def health_check(self) -> bool:
        """Pruefe ob der Collector funktionsfaehig ist."""
        return True
