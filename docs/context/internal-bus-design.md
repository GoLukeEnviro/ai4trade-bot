# Internal Event Bus -- Design

**Status:** Interface implementiert (Phase 1.4), nicht aktiv
**Datum:** 2026-05-29
**Geltungsbereich:** AI4Trade Bot -- Interne Event-Kommunikation

---

## 1. Uebersicht

Der interne Event Bus entkoppelt Pipeline-Komponenten ueber ein Publish/Subscribe-Pattern. Aktuell ist der Bus als Interface vorhanden (`NoOpEventBus`), aber nicht aktiv. Die Polling-Loop bleibt das primaere Ausfuehrungsmodell bis Event-Driven Architektur erforderlich wird.

---

## 2. Event-Flow

```
MarketEvent -> StrategyEvent -> RiskEvent -> ExecutionEvent -> AuditEvent
```

| Event-Typ | Ausloeser | Daten |
|-----------|-----------|-------|
| `MARKET` | OHLCV-Daten empfangen | pair, ohlcv, price |
| `STRATEGY` | Signal generiert | ta_result, sentiment, signal |
| `RISK` | Risk-Check abgeschlossen | passed, reason |
| `EXECUTION` | Order ausgefuehrt | order_result, mode |
| `AUDIT` | Audit-Eintrag geschrieben | event_type, details |

---

## 3. Implementierung (`core/events.py`)

### EventBus Protocol

```python
class EventBus(Protocol):
    def publish(self, event: Event) -> None: ...
    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None: ...
```

### Verfuegbare Implementierungen

| Klasse | Zweck | Status |
|--------|-------|--------|
| `NoOpEventBus` | MVP-Placeholder, loggt Debug | Aktiv (Default) |
| `InMemoryEventBus` | Thread-safe In-Memory fuer Tests | Verfuegbar |

### Event-Dataclass

```python
@dataclass(frozen=True)
class Event:
    event_type: EventType
    payload: dict
    correlation_id: str = ""
    causation_id: str = ""
    timestamp: float
```

---

## 4. Aktivierungs-Strategie

### Wann Event-Driven?

- **WebSocket-Integration:** Echtzeit-Marktdaten erfordern reaktive Verarbeitung
- **Multi-Strategy:** Parallele Strategien auf demselben Market-Event
- **External Integrations:** Webhook-Consumer, externe Signal-Quellen
- **Performance:** Polling-Loop wird zum Bottleneck

### Aktivierungspfad

1. `InMemoryEventBus` in `main.py` instanziieren
2. Handler fuer jeden Event-Typ registrieren
3. Polling-Loop publishes `MARKET` Events statt direkter Aufrufe
4. Schrittweise Migration: eine Komponente nach der anderen

---

## 5. Begruendung: Polling bleibt

- 60s Intervall ist ausreichend fuer Signal-Generierung
- Event-Driven bringt Komplexitaet (Reihenfolge, Fehlerpropagation, Backpressure)
- MVP-Prinzip: Einfachheit vor Skalierbarkeit
- Interface ist vorbereitet -- Aktivierung ohne Breaking Changes

---

## 6. Aenderungshistorie

| Datum | Aenderung | Phase |
|-------|-----------|-------|
| 2026-05-29 | Design-Dokumentation | 1.4 |
