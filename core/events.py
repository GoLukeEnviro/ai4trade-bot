import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

log = logging.getLogger(__name__)


class EventType(Enum):
    MARKET = "market"
    STRATEGY = "strategy"
    RISK = "risk"
    EXECUTION = "execution"
    AUDIT = "audit"


@dataclass(frozen=True)
class Event:
    event_type: EventType
    payload: dict
    correlation_id: str = ""
    causation_id: str = ""
    timestamp: float = field(default_factory=time.time)


class EventBus(Protocol):
    """Interface fuer Event-Bus. Spaeter implementierbar."""

    def publish(self, event: Event) -> None:
        """Event veroeffentlichen."""
        ...

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Handler fuer Event-Typ registrieren."""
        ...


class NoOpEventBus:
    """Placeholder fuer MVP. Tut nichts, loggt Debug."""

    def publish(self, event: Event) -> None:
        log.debug("EventBus nicht aktiv. Event %s ignoriert.", event.event_type.value)

    def subscribe(self, event_type: EventType, handler=None) -> None:
        log.debug("EventBus nicht aktiv. Subscribe fuer %s ignoriert.", event_type.value)


class InMemoryEventBus:
    """
    Einfache In-Memory Implementierung fuer Tests und spaetere Aktivierung.
    Synchron, Thread-safe via Lock.
    """

    def __init__(self):
        self._handlers: dict[EventType, list[Callable[[Event], None]]] = {}
        self._events: list[Event] = []

    def publish(self, event: Event) -> None:
        self._events.append(event)
        for handler in self._handlers.get(event.event_type, []):
            try:
                handler(event)
            except Exception as e:
                log.warning("Event handler error: %s", e)

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def get_events(self, event_type: EventType | None = None) -> list[Event]:
        if event_type is None:
            return list(self._events)
        return [e for e in self._events if e.event_type == event_type]

    def clear(self) -> None:
        self._events.clear()
