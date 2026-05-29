# AI4Trade Bot v0.2.0 -- Hybrid REST-Core + MCP-Ops-Layer

**Status:** Living Document
**Datum:** 2026-05-29
**Version:** 0.2.0
**Geltungsbereich:** Architektur-Dokumentation fuer den AI4Trade Bot

---

## 1. Uebersicht

Der AI4Trade Bot ist ein modularen Monolith in Python, der als **hybrider Signal-Generator** fuer Krypto-Trading fungiert. Er verbindet technische Analyse (TA) mit KI-gestuetzter Sentiment-Analyse und generiert Handelssignale fuer die AI4Trade-Simulated-Trading-Plattform.

### Architektur-Grundprinzipien

1. **REST-Core fuer Trading** -- Die Trading-Loop nutzt Bitget REST v2 fuer Marktdaten
2. **MCP-Ops-Layer fuer Agenten** -- MCP bietet read-only Marktdaten fuer KI-Agenten
3. **Strikte Trennung** -- MCP hat keinen Execution-Pfad, die Trading-Loop ist unabhaengig von MCP
4. **Fail-Closed Security** -- 4-lagige dry_run-Absicherung, Policy Engine, Circuit Breaker

### Versionshistorie

| Version | Status | Fokus |
|---------|--------|-------|
| v0.1.0 | MVP | Basis-Architektur, Binance, 113 Tests |
| v0.2.0 | Produktionsnaehe | Bitget-Migration, Persistenz, CI/CD, Safety, Execution, Docker |

---

## 2. Architektur-Diagramm

```
+------------------+     +-------------------+
|  MCP Agents      |     | Prometheus/       |
|  (Read-Only)     |     | Grafana           |
|  bitget-mcp-     |     | Monitoring        |
|  server          |     +-------------------+
+------------------+            ^
       |                        |
       | KEIN Execution-Pfad    | Metriken
       v                        |
+------------------+     +------+------+
|  Safety Gateway  |<----|  Trading   |<---- OHLCV (Bitget REST v2)
|  Policy Engine   |     |  Loop      |<---- Sentiment (Claude/OpenAI)
+------------------+     +------+------+
       |                        |
       v                        v
+------------------+     +-------------------+     +------------------+
|  Circuit         |     |  Execution        |     |  Bitget          |
|  Breaker         |     |  Service          |---->|  REST v2         |
|  (Portfolio)     |     |  OrderExecutor    |     |  api.bitget.com  |
+------------------+     |  ShadowExecutor   |     +------------------+
                         +-------------------+
                                |
         +----------------------+----------------------+
         |                      |                      |
         v                      v                      v
+------------------+   +------------------+   +------------------+
|  SQLite          |   |  Audit Trail     |   |  AI4Trade       |
|  Repository      |   |  (audit_log)     |   |  API            |
|  (signals,       |   +------------------+   |  (Publishing)   |
|   app_state)     |                           +------------------+
+------------------+
```

### Datenfluss-Diagramm

```
Bitget REST v2                        CryptoCompare
    |                                      |
    v                                      v
+----------+    +------------+    +----------------+
| Market   |--->| Technical  |    | Sentiment     |
| Data     |    | Analyzer   |    | Analyzer      |
| (OHLCV)  |    | (RSI/MACD/ |    | (Claude/OpenAI|
+----------+    |  EMA/BB)   |    |  + Guardrails)|
                +-----+------+    +-------+--------+
                      |                    |
                      v                    v
                +---------------------------+
                |  Strategy (Hybrid)        |
                |  TA 70% + Sentiment 30%   |
                +-------------+-------------+
                              |
                              v
                       +------------+
                       | Risk Gate  |
                       +------+-----+
                              |
                              v
                  +-----------------------+
                  | Circuit Breaker       |
                  | (Portfolio-Level)     |
                  +-----------+-----------+
                              |
                              v
                  +-----------------------+
                  | Safety Gateway        |
                  | (Policy Engine)       |
                  +-----------+-----------+
                              |
                              v
                  +-----------------------+
                  | Execution Service     |
                  | (OrderExecutor /      |
                  |  ShadowExecutor)      |
                  +-----------+-----------+
                              |
                    +---------+---------+
                    |                   |
                    v                   v
            +-------------+     +-------------+
            | AI4Trade    |     | Audit Trail |
            | Publisher   |     | (SQLite)    |
            +-------------+     +-------------+
```

---

## 3. Komponenten-Uebersicht

### 3.1 Trading Loop -- `main.py`

Der Orchestrator steuert den gesamten Signal-Generierungszyklus.

| Aspekt | Detail |
|--------|--------|
| Zykluszeit | `DATA_INTERVAL` (Default: 60s) |
| Signal-Pipeline | OHLCV -> TA -> Sentiment -> Strategy -> RiskGate -> Router |
| Heartbeat | Daemon-Thread (30s), Circuit Breaker nach 3 Fehlern |
| Shutdown | SIGINT/SIGTERM -> Queue-Flush (5s Timeout) |
| Persistenz | SQLite fuer Signale, State, Audit-Log |
| Logging | JSON oder Text, konfigurierbar ueber `LOG_FORMAT` |

### 3.2 Exchange -- `exchanges/bitget_rest.py`

Bitget REST v2 Client als primaere Marktdaten-Quelle.

| Methode | Endpoint | Zweck |
|---------|----------|-------|
| `get_ohlcv()` | `/api/v2/spot/market/candles` | OHLCV-Kerzendaten |
| `get_price()` | `/api/v2/spot/market/tickers` | Aktuelle Preise |

Eigenschaften:
- Retry mit Exponential Backoff (3 Versuche)
- Rate-Limiting via `TokenBucketRateLimiter`
- Symbol-Normalisierung (BTC/USDT -> BTCUSDT)
- Austauschbar ueber Exchange-Factory-Pattern (`exchanges/factory.py`)

### 3.3 AI Domain -- `ai/`

Isolierter AI-Bereich mit Provider-Abstraktion und Guardrails.

| Komponente | Datei | Zweck |
|------------|-------|-------|
| Provider-Interface | `ai/providers/base.py` | Abstraktes LLM-Interface |
| Claude Provider | `ai/providers/claude_provider.py` | Anthropic Claude API |
| OpenAI Provider | `ai/providers/openai_provider.py` | OpenAI-kompatible APIs |
| Provider-Factory | `ai/providers/factory.py` | Auswahl via `LLM_PROVIDER` |
| Sentiment | `ai/sentiment.py` | Sentiment-Analyse mit LLM |
| Guardrails | `ai/guardrails.py` | Score-Clamping, JSON-Parsing |
| Validation | `ai/validation.py` | Response-Validierung |

**Wichtige Regel:** AI-Calls duerfen NUR aus `ai/` heraus erfolgen. Keine direkten LLM-Aufrufe in anderen Modulen.

### 3.4 Execution -- `execution/`

Order-Ausfuehrung mit mehrstufiger Sicherheitspruefung.

| Komponente | Datei | Zweck |
|------------|-------|-------|
| OrderExecutor | `execution/order_executor.py` | Circuit Breaker -> Safety -> Publish |
| ShadowExecutor | `execution/shadow_executor.py` | Simulierte Trades mit PnL-Tracking |
| Execution Guards | `execution/execution_guards.py` | Letzte Validierung vor Order |
| Execution Models | `execution/execution_models.py` | OrderRequest, OrderResult, Status |
| Execution Audit | `execution/execution_audit.py` | Audit-Trail fuer Ausfuehrungen |

**Ablauf (OrderExecutor):**
1. Circuit Breaker Check -> REJECTED wenn aktiv
2. Safety Gateway Check -> REJECTED bei Policy-Verletzung
3. HOLD-Signal -> SKIPPED
4. Publisher -> SUBMITTED (dry_run) oder FILLED
5. Fehler -> FAILED

### 3.5 Safety -- `trading/safety_gateway.py`

Policy-basierte Sicherheits-Engine mit Fail-Closed-Prinzip.

| Aspekt | Detail |
|--------|--------|
| Architektur | Plugin-basiert: Policies implementieren `Policy`-Interface |
| Auswertung | Alle Policies pruefen, Worst-Case entscheidet |
| Severity-Level | INFO -> WARN -> BLOCK -> PANIC |
| PANIC | Short-Circuit: Sofortige Ablehnung |
| Audit | Jede Evaluierung wird geloggt |

**Verfuegbare Policies:**

| Policy | Datei | Zweck |
|--------|-------|-------|
| SymbolWhitelist | `trading/policies/symbol_whitelist.py` | Nur erlaubte Trading-Paare |
| MaxPositionSize | `trading/policies/max_position_size.py` | Positionsgrößen-Limit |
| MaxDrawdown | `trading/policies/max_drawdown.py` | Maximaler Drawdown |
| MaxDailyLoss | `trading/policies/max_daily_loss.py` | Taegliches Verlustlimit |
| MaxOrderFrequency | `trading/policies/max_order_frequency.py` | Order-Frequenz-Limit |
| ManualApproval | `trading/policies/manual_approval.py` | Manuelle Freigabe erforderlich |

### 3.6 Circuit Breaker -- `trading/portfolio_circuit_breaker.py`

Portfolio-Level Schutzmechanismus mit persistenter State.

| Ausloeser | Default | Massnahme |
|-----------|---------|-----------|
| Consecutive Losses | 5 Trades | HARD STOP |
| Daily Loss | 10% | HARD STOP |
| API Latency P99 | 10s | HARD STOP |
| Rejected Rate | 10% | HARD STOP |

Nach Ausloesung: Nur HOLD-Signale erlaubt, manuelle Reaktivierung noetig. State wird in `app_state`-Tabelle persistiert.

### 3.7 Persistence -- `storage/sqlite_repository.py`

SQLite-basierte Persistenz mit Repository-Pattern.

| Tabelle | Zweck |
|---------|-------|
| `signals` | Signal-Historie mit Trace-/Correlation-IDs |
| `app_state` | Key-Value Store fuer Bot-Zustand |
| `audit_log` | Unvernderlicher Audit-Trail |

Eigenschaften: WAL-Mode, Thread-safe (Lock), Repository-Interface fuer Austauschbarkeit.

### 3.8 Secret Management -- `core/secret_provider.py`

Drei-Backends fuer Credential-Speicherung.

| Backend | `SECRET_BACKEND` | Beschreibung |
|---------|------------------|--------------|
| `EnvSecretProvider` | `env` (Default) | Umgebungsvariablen |
| `KeyringSecretProvider` | `keyring` | OS-Keyring mit Env-Fallback |
| `VaultSecretProvider` | `vault` | HashiCorp Vault mit Env-Fallback |

### 3.9 Monitoring -- `core/metrics.py`

Prometheus-Metriken fuer alle Betriebsaspekte.

| Metrik | Typ | Zweck |
|--------|-----|-------|
| `bot_signals_total` | Counter | Generierte Signale (pair, action) |
| `bot_signals_published_total` | Counter | Published Signale |
| `bot_signals_blocked_total` | Counter | Blockierte Signale (pair, reason) |
| `bot_api_latency_seconds` | Histogram | API-Latenz (endpoint) |
| `bot_api_errors_total` | Counter | API-Fehler |
| `bot_drawdown_pct` | Gauge | Aktueller Drawdown |
| `bot_open_positions` | Gauge | Offene Positionen |
| `bot_circuit_breaker_active` | Gauge | Circuit Breaker Status |
| `bot_rate_limit_waits_total` | Counter | Rate-Limiter Wartezeiten |
| `bot_uptime_seconds` | Gauge | Bot-Uptime |
| `bot_info` | Gauge | Bot-Info (mode, version) |

Export: `METRICS_PORT` (Default: 9090).

### 3.10 Health Check -- `core/health.py`

Komponenten-Health mit aggregiertem Status.

| Komponente | Check |
|------------|-------|
| Database | Repository-Query (_health_check) |
| Exchange | `get_price("BTCUSDT")` gegen Bitget |
| AI4Trade API | `get_me()` gegen AI4Trade |

Status: `healthy` nur wenn ALLE Komponenten OK.

### 3.11 Infrastructure

| Komponente | Zweck |
|------------|-------|
| Docker | Containerisierung (`docker-compose.yml`) |
| Prometheus | Metriken-Scraping |
| Grafana | Dashboard-Visualisierung |
| AlertManager | Alert-Routing |
| Backup-Cron | Staendliche SQLite-Backups (`scripts/backup.sh`) |

---

## 4. Signal-Flow (Detail)

```
[1] Bitget REST v2 -> MarketData.get_ohlcv() -> OHLCV DataFrame
        |
[2] OHLCV -> TechnicalAnalyzer.analyze() -> TA-Signal (BUY/SELL/HOLD + Strength 0-100)
        |
[3] CryptoCompare -> SentimentAnalyzer.fetch_headlines() -> News
        |
[4] News -> LLM Provider (Claude/OpenAI) -> Sentiment-Score [-1.0, +1.0]
        |
[5] TA-Signal + Sentiment -> Strategy.decide() -> Signal (Action + Confidence)
        |
        |   Sentiment-Modifier:
        |     BUY:  confidence = ta_strength * (1 + sentiment_score * 0.3)
        |     SELL: confidence = ta_strength * (1 - sentiment_score * 0.3)
        |     HOLD: bleibt HOLD
        |
[6] Signal -> RiskGate.check() -> PASS / REJECT
        |
[7] PASS -> Circuit Breaker.check_signal() -> ALLOWED / BLOCKED
        |
[8] ALLOWED -> SafetyGateway.evaluate() -> PASSED / BLOCKED / PANIC
        |
[9] PASSED -> OrderExecutor.execute()
        |     -> SignalPublisher.publish() -> AI4Trade API
        |     -> SqliteSignalRepository.save_signal() -> SQLite
        |     -> SqliteSignalRepository.log_audit() -> Audit Trail
        |
[10] Metriken: Prometheus-Counter/Gauges aktualisiert
```

---

## 5. Sicherheits-Architektur

### 5.1 4-Layer dry_run Enforcement

| Layer | Ort | Mechanismus |
|-------|-----|-------------|
| 1 | `config.py` | `MODE`-Default ist `dry_run` |
| 2 | `signal_model.py` | `Signal.__post_init__` erzwingt `mode="dry_run"` |
| 3 | `signal_model.py` | `Intent.__post_init__` erzwingt `mode="dry_run"` |
| 4 | `main.py` | `run()` rejected wenn `MODE != "dry_run"` |

### 5.2 Secret Provider (Env/Keyring/Vault)

```
.env / OS-Keyring / HashiCorp Vault
         |
         v
create_secret_provider() -> SecretProvider
         |
         v
config.py: _secret_provider.get("API_KEY")
         |
         v
Niemals im Code, niemals in Logs, niemals in Diffs
```

### 5.3 Safety Gateway mit Policy Engine

```
Signal -> SafetyGateway.evaluate(signal, context)
              |
              +-> Policy 1: SymbolWhitelist.check()
              +-> Policy 2: MaxPositionSize.check()
              +-> Policy 3: MaxDrawdown.check()
              +-> Policy 4: MaxDailyLoss.check()
              +-> Policy 5: MaxOrderFrequency.check()
              +-> Policy 6: ManualApproval.check()
              |
              v
         Worst-Case Result: INFO | WARN | BLOCK | PANIC
```

Fail-Closed: Jede Policy-Instanz kann ein Signal ablehnen. PANIC fuehrt zu sofortigem Abbruch.

### 5.4 Portfolio Circuit Breaker

Persistenter Zustand in SQLite. Nach Ausloesung:
- Nur HOLD-Signale erlaubt
- Manuelle Reaktivierung erforderlich (`deactivate()`)
- Metrik `bot_circuit_breaker_active` = 1
- Audit-Eintrag `circuit_breaker_activated`

### 5.5 2FA fuer Live-Modus

TOTP-basierte Zwei-Faktor-Authentifizierung (`core/two_factor.py`):
- `pyotp` Bibliothek fuer TOTP-Generierung/Verifikation
- `TOTP_SECRET` ueber Secret Provider
- Verifikation mit `valid_window=1` (30s Toleranz)

### 5.6 Audit Trail

Alle sicherheitsrelevanten Ereignisse werden in `audit_log`-Tabelle gespeichert:

| Event | Ausloeser |
|-------|-----------|
| `bot_start` / `bot_stop` | Lifecycle |
| `policy_*` | Safety Gateway Evaluierung |
| `circuit_breaker_activated/deactivated` | Circuit Breaker |
| `execution_*` | Order-Ausfuehrung |
| `shadow_trade_*` | Shadow Mode |

### 5.7 MCP-Sicherheit

MCP ist architektonisch vom Trading-Kanal getrennt:

```
MCP (bitget-mcp-server)          Trading-Loop
  |                                  |
  +-- Nur market-Modul               +-- Bitget REST v2
  +-- Kein Trade-Modul               +-- Execution Service
  +-- Kein Account-Modul             +-- Safety Gateway
  +-- Kein Execution-Pfad            +-- Circuit Breaker
```

Siehe `docs/context/bitget-mcp-setup.md` fuer Details.

---

## 6. Architektur-Entscheidungen (ADRs)

### ADR-1: Bitget als primaere Exchange

**Kontext:** v0.1.0 nutzte Binance. GAP-25 forderte Bitget-Alignment.

**Entscheidung:** Migration auf Bitget REST v2 als primaere Marktdaten-Quelle.

**Konsequenzen:**
- `exchanges/bitget_rest.py` als neue Implementierung
- Exchange-Factory-Pattern fuer kuenftige Austauschbarkeit
- CoinGecko bleibt als sekundaere Quelle in `core/market_data.py`
- Symbol-Format: BTCUSDT (ohne Slash)

### ADR-2: REST statt WebSocket

**Kontext:** Echtzeit-Marktdaten vs. Einfachheit.

**Entscheidung:** REST-Polling (60s) fuer MVP. WebSocket ist vorbereitet aber nicht implementiert.

**Begruendung:** 60s Intervall reicht fuer Signal-Generierung. WebSocket bringt Komplexitaet (Connection-Management, Reconnect), die im MVP nicht gerechtfertigt ist.

### ADR-3: SQLite jetzt, austauschbar spaeter

**Kontext:** Persistenz war in v0.1.0 nicht vorhanden (GAP-01).

**Entscheidung:** SQLite mit Repository-Pattern. Interface in `storage/repository.py`, Implementierung in `storage/sqlite_repository.py`.

**Begruendung:** SQLite ist zero-config, single-file, ausreichend fuer Single-Instance. Repository-Pattern ermoeglicht spaeteren Wechsel auf PostgreSQL/Redis ohne Aenderungen an der Business-Logik.

### ADR-4: AI Isolation Layer

**Kontext:** LLM-Calls waren urspruenglich direkt in `core/sentiment.py`.

**Entscheidung:** Alle AI-Funktionalitaet wird ueber das `ai/`-Package abstrahiert.

**Begruendung:**
- Provider-Austauschbarkeit (Claude, OpenAI, kuenftige)
- Guardrails zentralisiert (`ai/guardrails.py`)
- Validierung zentralisiert (`ai/validation.py`)
- Keine AI-Calls ausserhalb von `ai/`

### ADR-5: Policy Engine statt hardcoded if-statements

**Kontext:** Risk-Gate hatte feste if-Pruefungen.

**Entscheidung:** Plugin-basierte Policy Engine in `trading/policies/`.

**Begruendung:**
- Neue Policies ohne Aenderung an bestehendem Code
- Jede Policy ist unabhaengig testbar
- Severity-Level (INFO/WARN/BLOCK/PANIC) statt binar
- Audit pro Policy-Evaluierung

### ADR-6: Shadow Mode als Pflicht vor Live

**Kontext:** Direkter Sprung von dry_run zu Live-Modus ist zu riskant.

**Entscheidung:** `ShadowExecutor` simuliert Trades mit echten Marktdaten und trackt Performance.

**Begruendung:**
- Validierung der Signal-Qualitaet mit echten Marktdaten
- Win-Rate, PnL-Tracking ohne finanzielles Risiko
- Mindestens 30 Tage Shadow Mode vor Live-Freigabe
- Performance-Metriken als Go/No-Go-Kriterium

---

## 7. Produktions-Caveats

### 7.1 Bot ist noch dry_run-only

Der Bot operiert ausschliesslich im Simulationsmodus. Keine echten Orders werden ausgefuehrt. Die 4-lagige dry_run-Absicherung verhindert unbeabsichtigtes Live-Trading.

### 7.2 Live-Modus braucht 30+ Tage Shadow Mode

Vor einer Live-Aktivierung MUSS der Shadow Mode mindestens 30 Tage laufen mit:
- Positiver Win-Rate (>50%)
- Positivem Gesamt-PnL
- Keinen kritischen Circuit Breaker-Ausloesungen
- Erfolgreichem Sicherheitsaudit

### 7.3 MCP darf niemals direkt traden

MCP hat architektonisch keinen Zugriff auf das Trading-Modul. Das `--modules market` Flag stellt sicher, dass nur Leseoperationen moeglich sind. Selbst bei Kompromittierung bleibt der Trading-Kanal geschuetzt.

### 7.4 Backup-Cron muss konfiguriert sein

Ohne Backup-Cron gibt es keine automatischen SQLite-Backups. Bei Datenverlust sind alle Signale und Audit-Eintraege verloren. Siehe `docs/recovery.md` fuer Backup- und Recovery-Prozedur.

### 7.5 Prometheus muss laufen

Metriken werden nur exportiert wenn der Bot laeuft. Ohne Prometheus-Scraping gehen Metriken bei Bot-Neustart verloren. AlertManager muss korrekt konfiguriert sein.

### 7.6 Rate Limiter konfigurieren

Default-Rate-Limits sind konservativ. Bei haeufigeren Abfragen muessen die `RATE_LIMIT_*`-Variablen angepasst werden. Zu aggressive Limits koennen zu API-Bans fuehren.

---

## 8. Verweise

| Dokument | Ort | Zweck |
|----------|-----|-------|
| MCP Setup | `docs/context/bitget-mcp-setup.md` | MCP-Konfiguration |
| Backup & Recovery | `docs/recovery.md` | Backup/Recovery-Prozedur |
| GAP-Auditbericht | `docs/audit/GAP-Auditbericht-ai4trade-bot.md` | GAP-Analyse v0.1.0 |
| Betriebs-Doku | `docs/operations.md` | Start/Stop, Konfiguration, Monitoring |
| Incident Response | `docs/incident-response.md` | Incident-Handling |
| Design-Spec | `docs/superpowers/specs/2026-05-07-ai4trade-bot-design.md` | Urspruenglicher Entwurf |
| README | `README.md` | Projekt-Uebersicht |
| Changelog | `CHANGELOG.md` | Versionshistorie |

---

## 9. Aenderungshistorie

| Datum | Aenderung | Version |
|-------|-----------|---------|
| 2026-05-29 | Initiale Erstellung | v0.2.0 |
