# Replay Engine -- Konzept

**Status:** Konzept, nicht implementiert
**Datum:** 2026-05-29
**Geltungsbereich:** AI4Trade Bot -- Historische Daten fuer Backtesting und Analyse

---

## 1. Uebersicht

Die Replay Engine ermoeglicht das Abspielen historischer Daten durch die Pipeline. Drei Replay-Modi sind geplant: Candle-Replay, Strategy-Replay und AI-Replay. Die Grundlagen (Correlation IDs, append-only Audit) sind bereits implementiert.

---

## 2. Replay-Modi

### 2.1 Candle-Replay

Historische OHLCV-Daten werden durch die Strategy geleitet.

```
Historische OHLCV -> TechnicalAnalyzer -> Strategy -> Signal
```

- **Datenquelle:** Bitget REST API historische Candles
- **Zeitraum:** Konfigurierbar (z.B. letzte 30 Tage)
- **Geschwindigkeit:** Zeitraffer (1 Candle pro Sekunde statt pro Minute)
- **Ergebnis:** Signal-Historie mit Metriken (Win-Rate, PnL)

### 2.2 Strategy-Replay

Gespeicherte TA-Results + Sentiment werden durch die Strategy geleitet.

```
Gespeichertes TA-Result + Sentiment -> Strategy -> Signal
```

- **Voraussetzung:** TA- und Sentiment-Ergebnisse muessen gespeichert sein (Snapshots)
- **Vergleich:** Neues Signal vs. historisches Signal
- **Zweck:** Strategy-Aenderungen validieren

### 2.3 AI-Replay

Gespeicherte Prompts werden an das LLM gesendet und Ergebnisse verglichen.

```
Gespeicherter Prompt -> LLM Provider -> Sentiment -> Vergleich
```

- **Voraussetzung:** Prompts und Ergebnisse muessen geloggt sein
- **Vergleich:** Neues Sentiment vs. historisches Sentiment
- **Zweck:** Provider-Wechsel oder Prompt-Aenderung validieren

---

## 3. Vorbereitete Grundlagen

| Komponente | Status | Datei |
|------------|--------|-------|
| Correlation IDs | Implementiert | `storage/sqlite_repository.py` |
| Append-only Audit | Implementiert | `storage/sqlite_repository.py` |
| Event-Bus Interface | Implementiert | `core/events.py` |
| Strategy Interface | Implementiert | `core/strategy.py` |
| TA-Analyzer | Implementiert | `core/technical_analyzer.py` |
| Sentiment Analyzer | Implementiert | `ai/sentiment.py` |

---

## 4. Was noch fehlt

### Snapshots

- TA-Results speichern (aktuell nur im Log)
- Sentiment-Results speichern inkl. Prompt
- `trace_id` in `audit_log` Tabelle

### Replay-Infrastruktur

- `replay/` Package mit CandlePlayer, StrategyReplayer, AIReplayer
- Zeitstempel-Normalisierung (historische -> simulierte Zeit)
- Metriken-Aggregation (Win-Rate, Sharpe, Max-Drawdown)
- Vergleichs-Report (neu vs. historisch)

### Schema-Erweiterung

```sql
-- Zukuenftig: Snapshots speichern
CREATE TABLE ta_snapshots (
    id INTEGER PRIMARY KEY,
    trace_id TEXT,
    pair TEXT,
    result_json TEXT,
    created_at TEXT
);

CREATE TABLE sentiment_snapshots (
    id INTEGER PRIMARY KEY,
    trace_id TEXT,
    pair TEXT,
    prompt_text TEXT,
    result_json TEXT,
    created_at TEXT
);
```

---

## 5. Prioritaet

Replay Engine ist **nicht** fuer das MVP geplant. Sie wird relevant wenn:
- Shadow Mode Daten fuer Backtesting verfuegbar sind (>30 Tage)
- Strategy-Aenderungen validiert werden muessen
- Provider-Wechsel (Claude -> OpenAI) verglichen werden sollen

---

## 6. Aenderungshistorie

| Datum | Aenderung | Phase |
|-------|-----------|-------|
| 2026-05-29 | Konzept-Dokumentation | -- |
