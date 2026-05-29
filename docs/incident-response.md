# AI4Trade Bot -- Incident-Response-Dokumentation

**Status:** Living Document
**Datum:** 2026-05-29
**Version:** 0.2.0
**Geltungsbereich:** Incident-Handling, Emergency-Prozeduren, Eskalation

---

## 1. Severity Levels

Alle Systemereignisse werden nach folgendem Schema klassifiziert:

| Level | Bedeutung | Beispiele | Benachrichtigung |
|-------|-----------|-----------|-----------------|
| **INFO** | Normalbetrieb, keine Aktion noetig | Signal generiert, Bot gestartet, Backup erstellt | Logging |
| **WARN** | Potenzielles Problem, Beobachtung empfohlen | Erhoehte API-Latenz, Drawdown >15%, Backup verpasst | Logging + Alert |
| **BLOCK** | Signal blockiert, Bot laeuft weiter | Safety-Gate-Verletzung, Risk-Gate-Verletzung, Rate-Limit erreicht | Logging + Alert |
| **PANIC** | Kritischer Vorfall, sofortiges Handeln erforderlich | Circuit Breaker ausgeloest, DB korrupt, Exchange teljes Ausfall | Logging + Alert + Eskalation |

### Severity in Policies

Das Safety Gateway (`trading/safety_gateway.py`) verwendet dieselben Level:

| Severity | Verhalten |
|----------|-----------|
| `INFO` | Bestanden, Log-Eintrag |
| `WARN` | Bestanden, aber Warnung |
| `BLOCK` | Signal abgelehnt |
| `PANIC` | Sofortige Ablehnung, Short-Circuit |

---

## 2. Circuit Breaker Response

### 2.1 Erkennen

**Indikatoren:**
- Metrik `bot_circuit_breaker_active == 1`
- Log: `CIRCUIT BREAKER ACTIVATED: <reason>`
- Alert: `CircuitBreakerActive` feuert

**Moegliche Ausloeser:**

| Ausloeser | Default-Threshold | Bedeutung |
|-----------|-------------------|-----------|
| Consecutive Losses | 5 Trades | 5 aufeinanderfolgende Verlust-Trades |
| Daily Loss | 10% | Taeglicher Verlust ueber 10% |
| API Latency P99 | 10s | 99. Perzentil der API-Latenz ueber 10s |
| Rejected Rate | 10% | Mehr als 10% der Exchange-Requests abgelehnt |

### 2.2 Sofortmassnahmen

1. **Lage feststellen:** Audit-Log pruefen
   ```bash
   sqlite3 storage/bot.db "SELECT * FROM audit_log WHERE event_type LIKE '%circuit_breaker%' ORDER BY created_at DESC LIMIT 5"
   ```

2. **Ursache identifizieren:**
   - `consecutive losing trades` -> Strategie-Analyse noetig
   - `daily loss exceeds` -> Marktsituation pruefen
   - `API latency P99` -> Exchange/Netzwerk pruefen
   - `rejected rate` -> Rate-Limits, API-Status pruefen

3. **Entscheidung:**
   - Ursache behoben? -> Circuit Breaker manuell deaktivieren
   - Ursache unklar? -> Bot gestoppt lassen, Analyse fortsetzen

### 2.3 Circuit Breaker deaktivieren

**Nur nach Ursachen-Analyse und Fix:**

```python
# Interaktive Python-Session
from storage.sqlite_repository import SqliteSignalRepository
from trading.portfolio_circuit_breaker import PortfolioCircuitBreaker

repo = SqliteSignalRepository("storage/bot.db")
cb = PortfolioCircuitBreaker(repository=repo)
cb.deactivate()
repo.close()
```

**Alternativ:** Bot-Neustart mit zurueckgesetztem State (nur wenn Ursache behoben):
```bash
# State in DB zuruecksetzen
sqlite3 storage/bot.db "DELETE FROM app_state WHERE key LIKE 'circuit_breaker%'"
# Bot neustarten
docker compose restart
```

**WICHTIG:** Niemals den Circuit Breaker deaktivieren ohne die Ursache zu verstehen.

### 2.4 Praevention

- Monitoring auf `bot_drawdown_pct` und `bot_api_latency_seconds` einrichten
- Alerts bei DRAWDOWN > 15% und API P99 > 5s
- Regelmaessige Strategie-Performance-Reviews

---

## 3. Emergency Shutdown

### 3.1 Bot sofort stoppen

```bash
# Docker
docker compose down

# Systemd
sudo systemctl stop ai4trade-bot

# Lokal (wenn Terminal sichtbar)
Ctrl+C

# Lokal (Hintergrundprozess)
kill -SIGTERM <PID>
# Letzte Option:
kill -9 <PID>
```

### 3.2 Naechste Schritte nach Emergency Shutdown

1. **Logs sichern:** `cp storage/bot.log storage/bot.log.emergency`
2. **DB sichern:** `cp storage/bot.db storage/bot.db.emergency`
3. **Ursache analysieren:** Logs und Audit-Trail durchsehen
4. **Fix implementieren:** Ursache beheben
5. **Validieren:** Tests ausfuehren (`pytest`)
6. **Neustarten:** Bot wieder hochfahren
7. **Verifizieren:** Health-Check und Metriken pruefen

### 3.3 Wann Emergency Shutdown erforderlich

| Situation | Massnahme |
|-----------|-----------|
| Bot generiert unerklaerliche Signale | Sofort stoppen, Strategie pruefen |
| Circuit Breaker wiederholt ausgeloest | Stoppen, Ursache analysieren |
| Exchange meldet unautorisierte Zugriffe | Stoppen, API-Key rotieren |
| Datenbank korrupt | Stoppen, Recovery-Prozedur |
| Unbekannter Fehler im Hauptthread | Stoppen, Logs analysieren |

---

## 4. Recovery von korrupter DB

### 4.1 Symptome

- `sqlite3.OperationalError: database disk image is malformed`
- `PRAGMA integrity_check` liefert nicht `ok`
- Bot startet nicht mit DB-Fehlern

### 4.2 Recovery-Prozedur

**Schritt 1: Bot stoppen**

```bash
docker compose down
```

**Schritt 2: Korrupte DB sichern**

```bash
cp storage/bot.db storage/bot.db.corrupted.$(date +%Y%m%d%H%M%S)
```

**Schritt 3: Reparatur-Versuch**

```bash
# Daten aus korrupter DB extrahieren
sqlite3 storage/bot.db.corrupted ".dump" | sqlite3 storage/bot_repaired.db

# Integritaet pruefen
sqlite3 storage/bot_repaired.db "PRAGMA integrity_check"
```

**Schritt 4: Wenn Reparatur erfolgreich**

```bash
mv storage/bot_repaired.db storage/bot.db
```

**Schritt 5: Wenn Reparatur fehlgeschlagen**

```bash
# Letztes funktionierendes Backup verwenden
ls -lht storage/backups/bot_*.db
cp storage/backups/bot_YYYYMMDD_HHMMSS.db storage/bot.db
```

Siehe `docs/recovery.md` fuer die vollstaendige Recovery-Prozedur mit Validierungsschritten.

**Schritt 6: Bot neustarten und validieren**

```bash
docker compose up -d
curl http://localhost:8080/health
sqlite3 storage/bot.db "PRAGMA integrity_check"
```

---

## 5. Exchange-Ausfall (Bitget)

### 5.1 Symptome

- Alle Bitget API-Calls schlagen fehl (HTTP 5xx oder Timeout)
- `bot_api_errors_total{endpoint="bitget"}` steigt
- Keine neuen Signale (fehlende OHLCV-Daten)
- Log: `Bitget API Fehler (Versuch 3/3)`

### 5.2 Automatische Reaktion

Der Bot hat eingebaute Resilienz:
- **Retry:** 3 Versuche mit Exponential Backoff (1s, 2s, 4s)
- **Rate Limiter:** Verhindert Ueberlastung bei Recovery
- **Heartbeat Circuit Breaker:** Pausiert Heartbeat bei 3 Fehlern (60s)

### 5.3 Manuelle Massnahmen

1. **Bitget Status pruefen:**
   ```bash
   curl -s https://api.bitget.com/api/v2/public/time
   ```

2. **Wenn Bitget down:**
   - Bot laeuft weiter, generiert aber keine Signale (keine Marktdaten)
   - Warten auf Recovery, Bot reconnectet automatisch
   - Drawdown bleibt unveraendert (keine Trades)

3. **Wenn Bitget teilweise verfuegbar:**
   - Einzelne Pairs koennen fehlschlagen
   - Logs pruefen: `grep "Bitget API Fehler" storage/bot.log`

4. **Wenn Rate-Limit getroffen (HTTP 429):**
   - `RATE_LIMIT_BITGET` in `.env` senken
   - Bot neustarten

### 5.4 Eskalation

| Dauer | Massnahme |
|-------|-----------|
| < 5 Minuten | Beobachten, automatischer Retry |
| 5-30 Minuten | Bitget Status-Seite pruefen, Logs beobachten |
| > 30 Minuten | Alert an Operator, Manuelle Entscheidung ueber Bot-Betrieb |
| > 2 Stunden | Bot stoppen, naehere Analyse, ggf. Fallback-Exchange evaluieren |

---

## 6. AI-Ausfall (Sentiment)

### 6.1 Symptome

- Sentiment-Score dauerhaft 0.0
- `bot_api_errors_total{endpoint="llm"}` steigt
- Log: `Sentiment-Analyse fehlgeschlagen, nutze neutral`
- `LOG_LEVEL=DEBUG`: LLM-Response-Fehler sichtbar

### 6.2 Automatische Reaktion

Der Bot hat einen eingebauten Fallback:
- Sentiment-Score faellt auf 0.0 (neutral) zurueck
- TA-Signale werden unveraendert weiterverarbeitet
- Confidence wird nur durch TA bestimmt (Sentiment-Modifier = 0)
- Bot bleibt voll funktionsfaehig, nur ohne Sentiment-Booster

### 6.3 Manuelle Massnahmen

1. **LLM-API pruefen:**
   ```bash
   # Claude API
   python -c "from anthropic import Anthropic; print(Anthropic().messages.list())"

   # OpenAI-kompatibel
   curl -s $LLM_BASE_URL/models -H "Authorization: Bearer $LLM_API_KEY"
   ```

2. **API-Key validieren:**
   - `.env` pruefen: `CLAUDE_API_KEY` bzw. `LLM_API_KEY`
   - Guthaben/Quota beim Provider pruefen

3. **Provider wechseln:**
   ```bash
   # In .env
   LLM_PROVIDER=openai
   LLM_BASE_URL=https://api.openai.com/v1
   LLM_API_KEY=<key>
   LLM_MODEL=gpt-4o
   ```

4. **Bot neustarten** nach Konfigurationsaenderung

### 6.4 Auswirkung bei AI-Ausfall

| Aspekt | Mit Sentiment | Ohne Sentiment (Fallback) |
|--------|---------------|--------------------------|
| TA-Signal | Unveraendert | Unveraendert |
| Confidence | TA + Sentiment-Modifier | Nur TA-Strength |
| BUY-Signale | Sentiment kann Confidence erhoehen | Nur TA-basierte Confidence |
| SELL-Signale | Sentiment kann Confidence erhoehen | Nur TA-basierte Confidence |
| HOLD-Signale | Kein Unterschied | Kein Unterschied |
| Bot-Funktionalitaet | Voll | Voll (reduzierte Genauigkeit) |

---

## 7. Incident-Log-Vorlage

Jeder Incident sollte dokumentiert werden:

```
## Incident #NNN

| Feld | Wert |
|------|------|
| Datum | YYYY-MM-DD HH:MM |
| Severity | INFO/WARN/BLOCK/PANIC |
| Entdeckt durch | Alert/Manuell/Log |
| Betroffen | Bot/DB/Exchange/AI |
| Dauer | XX Minuten |
| Auswirkung | Beschreibung |
| Ursache | Root Cause |
| Massnahme | Was wurde getan |
| Praevention | Wie wird es verhindert |
| Bearbeiter | Name |
```

---

## 8. Eskalationsmatrix

| Severity | Reaktionszeit | Wer |
|----------|--------------|-----|
| INFO | Keine | Automatisch |
| WARN | < 1 Stunde | Operator (Monitoring) |
| BLOCK | < 30 Minuten | Operator |
| PANIC | < 15 Minuten | Operator + Tech-Lead |

### Eskalations-Pfad

```
Automatisches Monitoring
    |
    v
Operator (Level 1)
    |
    v (wenn nicht in 30min geloest)
Tech-Lead (Level 2)
    |
    v (wenn kritisch fuer den Betrieb)
Entscheider (Level 3)
```

---

## 9. Verweise

| Dokument | Ort |
|----------|-----|
| Architektur | `docs/context/bitget-mcp-hybrid-architecture.md` |
| Betriebs-Doku | `docs/operations.md` |
| Backup & Recovery | `docs/recovery.md` |
| MCP Setup | `docs/context/bitget-mcp-setup.md` |
| GAP-Auditbericht | `docs/audit/GAP-Auditbericht-ai4trade-bot.md` |

---

## 10. Aenderungshistorie

| Datum | Aenderung |
|-------|-----------|
| 2026-05-29 | Initiale Erstellung |
