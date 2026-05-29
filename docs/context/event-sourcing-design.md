# Event Sourcing Design -- Vorbereitung

**Status:** Vorbereitet (Phase 1.4 Audit-Tabellen)
**Datum:** 2026-05-29
**Geltungsbereich:** AI4Trade Bot -- Append-Only Audit als Event Sourcing Grundlage

---

## 1. Uebersicht

Die aktuellen Audit-Tabellen sind als append-only store designed und bilden die Grundlage fuer ein spaeteres Event Sourcing System. Kein Update oder Delete auf Audit-Daten -- der gesamte Zustand ist durch die Event-Historie rekonstruierbar.

---

## 2. Aktuelle Implementierung

### audit_log Schema (`storage/sqlite_repository.py`)

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    details_json TEXT,
    created_at TEXT DEFAULT (datetime('now'))
)
```

### Eigenschaften

- **Append-only:** Kein UPDATE oder DELETE auf `audit_log`
- **Event-Typisierung:** `event_type` kategorisiert Eintraege (z.B. `bot_start`, `policy_*`, `execution_*`)
- **JSON-Payload:** `details_json` speichert strukturierte Event-Daten
- **Zeitstempel:** `created_at` fuer chronologische Sortierung

### Geschriebene Event-Typen

| Event-Typ | Ausloeser | Phase |
|-----------|-----------|-------|
| `bot_start` / `bot_stop` | Lifecycle | 1.4 |
| `policy_*` | Safety Gateway | 3.4 |
| `circuit_breaker_*` | Circuit Breaker | 4.2 |
| `execution_*` | Order-Ausfuehrung | 4.3 |
| `shadow_trade_*` | Shadow Executor | 4.4 |

---

## 3. Event-Bus Interface

`core/events.py` definiert das Event Sourcing Interface:

- **`EventBus` Protocol:** `publish()` und `subscribe()` Methoden
- **`NoOpEventBus`:** MVP-Placeholder, loggt Debug-Meldungen
- **`InMemoryEventBus`:** Thread-safe In-Memory Implementierung fuer Tests
- **`Event` Dataclass:** `event_type`, `payload`, `correlation_id`, `causation_id`, `timestamp`

---

## 4. Weg zum Event Sourcing

### Bereit

- Append-only Audit-Tabelle
- Event-Bus Interface
- Event-Dataclass mit correlation_id und causation_id
- EventType Enum fuer Kategorisierung

### Noetig fuer Replay

- `trace_id` in `audit_log` Tabelle (aktuell nur in `signals`)
- Snapshot-Funktion fuer TA- und Sentiment-State
- Event-Store (SQLite oder dediziert) mit Index auf `trace_id`
- Replay-Engine (siehe `replay-engine-design.md`)

### Schema-Aenderung

```sql
-- Zukuenftig: trace_id Spalte in audit_log
ALTER TABLE audit_log ADD COLUMN trace_id TEXT DEFAULT '';
ALTER TABLE audit_log ADD COLUMN causation_id TEXT DEFAULT '';
```

---

## 5. Architektur-Entscheidung

Event Sourcing ist vorbereitet aber nicht aktiv. Die Polling-Loop bleibt das primaere Ausfuehrungsmodell. Der Event-Bus wird erst aktiviert, wenn Performance oder Replay-Faehigkeit es erfordern.

**Prinzip:** Audit-Daten sind Events. Events sind unveraenderlich. Unveraenderlichkeit ermoeglicht Replay.

---

## 6. Aenderungshistorie

| Datum | Aenderung | Phase |
|-------|-----------|-------|
| 2026-05-29 | Design-Dokumentation | 1.4 |
