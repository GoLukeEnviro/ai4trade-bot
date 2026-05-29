from __future__ import annotations

from abc import ABC, abstractmethod

from core.signal_model import Signal


class SignalRepository(ABC):
    @abstractmethod
    def save_signal(self, signal: Signal, trace_id: str = "", correlation_id: str = "") -> int:
        """Signal persistieren, Zeilen-ID zurueckgeben."""
        ...

    @abstractmethod
    def get_recent_signals(self, pair: str | None = None, limit: int = 50) -> list[dict]:
        """Letzte Signale abfragen, optional nach Pair gefiltert."""
        ...

    @abstractmethod
    def set_state(self, key: str, value: str) -> None:
        """Schluessel-Wert-Paar speichern (Upsert)."""
        ...

    @abstractmethod
    def get_state(self, key: str, default: str = "") -> str:
        """Wert fuer Schluessel laden, Default wenn nicht gefunden."""
        ...

    @abstractmethod
    def log_audit(self, event_type: str, details: dict | None = None) -> int:
        """Audit-Event protokollieren, Zeilen ID zurueckgeben."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Verbindung schliessen."""
        ...
