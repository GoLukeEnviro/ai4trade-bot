# Correlation IDs -- Traceability Design

**Status:** Implementiert (Phase 1.4)
**Datum:** 2026-05-29
**Geltungsbereich:** AI4Trade Bot -- Ereignisverfolgung ueber die gesamte Pipeline

---

## 1. Uebersicht

Correlation IDs ermoeglichen die Rueckverfolgung von Signalen und Events ueber alle Pipeline-Stufen. Jedes Signal erhaelt bei der Erstellung eindeutige IDs, die bis zum Audit-Trail durchgereicht werden.

---

## 2. ID-Typen

### 2.1 trace_id

- **Gueltigkeit:** Eindeutig pro Signal
- **Erzeugung:** UUID4 bei Signal-Erstellung in `main.py`
- **Verwendung:** Wird in `signals` Tabelle gespeichert und an alle nachfolgenden Komponenten uebergeben
- **Zweck:** Ein Signal ueber seinen gesamten Lebenszyklus verfolgen

### 2.2 correlation_id

- **Gueltigkeit:** Verknuepft zusammenhaengende Events
- **Erzeugung:** UUID4, kann mehrere Signale umfassen
- **Verwendung:** Gruppiert Events, die zum gleichen Entscheidungsprozess gehoeren
- **Zweck:** Zusammenhaengende Event-Ketten identifizieren (z.B. Signal + Risk-Check + Execution)

### 2.3 causation_id (zukuenftig)

- **Gueltigkeit:** Welches Event hat dieses ausgeloest
- **Status:** **Nicht implementiert** -- Feld im `Event`-Dataclass vorbereitet (`core/events.py`)
- **Zweck:** Kausalkette fuer Event Sourcing Replay
- **Benutzerungspaetere:** `Event(causation_id=parent_event.trace_id)`

---

## 3. Implementierung

### Tabellen-Schema (`signals`)

```sql
trace_id TEXT DEFAULT '',
correlation_id TEXT DEFAULT ''
```

Beide Felder werden beim `save_signal()`-Aufruf in `storage/sqlite_repository.py` gefuellt.

### Event-Dataclass (`core/events.py`)

```python
@dataclass(frozen=True)
class Event:
    event_type: EventType
    payload: dict
    correlation_id: str = ""
    causation_id: str = ""
    timestamp: float = field(default_factory=time.time)
```

`correlation_id` und `causation_id` sind im Event-Modell vorbereitet.

---

## 4. Verwendungsstellen

| Stelle | trace_id | correlation_id |
|--------|----------|----------------|
| `main.py` Signal-Erstellung | Ja (UUID4) | Ja (UUID4) |
| `storage/sqlite_repository.py` | Persistiert | Persistiert |
| `core/events.py` Event | -- | Ja (Feld) |
| Audit-Log | -- | -- (zukuenftig) |

---

## 5. Zukuenftige Erweiterung

- **causation_id** fuer Event Sourcing: Kausalkette von Event zu Event
- **trace_id in audit_log:** Aktuell hat `audit_log` keine `trace_id`-Spalte -- fuer Replay noetig
- **Distributed Tracing:** Wenn mehrere Bot-Instanzen laufen, koennen correlation_ids Instanz-uebergreifend verwendet werden

---

## 6. Aenderungshistorie

| Datum | Aenderung | Phase |
|-------|-----------|-------|
| 2026-05-29 | Design-Dokumentation | 1.4 |
