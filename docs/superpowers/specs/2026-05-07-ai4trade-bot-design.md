# AI4Trade Bot — Design Specification

**Datum:** 2026-05-07
**Status:** Draft v4 (Security Correction)
**Autor:** CodeLuke + Claude
**Kanonischer Projektpfad (Entwicklung):** `C:\Users\CodeLuke\ai4trade-bot`
**Kanonischer Projektpfad (VPS Runtime):** `/home/hermes/projects/trading/ai4trade-bot`

---

## 1. Vision

Ein modularer Monolith in Python, der als **AI4Trade Signal-Adapter + Sentiment-Analyst + Freqtrade-Brücke** fungiert. Kein eigenständiger Live-Trading-Executor — sondern ein intelligenter Signal-Generator, der auf der AI4Trade-Simulated-Trading-Plattform agiert und bestehende Systeme (Freqtrade, PrimoAgent) ergänzt.

### Kernprinzipien

1. **Kein direkter Order-Placement** — nur Signal-Weiterleitung an AI4Trade (simuliert)
2. **Standardmäßig dry-run-only** — Live-Modus ist für MVP out of scope. Nur über `.env` änderbar, nie über Chat.
3. **Claude-Chat = Intent-System** — erzeugt strukturierte JSON-Intents, keine direkten Handelsaktionen. `mode` ist IMMER `"dry_run"` — kein Chat-Befehl kann das ändern.
4. **Sentiment ist Modifier, nicht Entscheider** — TA primär, Sentiment passt Confidence an
5. **Freqtrade-Brücke optional** — MVP funktioniert standalone über AI4Trade-Simulated-Trading

### Security Incident Note

Während der Erstellung dieses Specs wurden Credentials (E-Mail, Passwort, JWT-Token) versehentlich in Terminal-Befehlen (`curl`) im Klartext ausgeführt. Diese sind im Chatverlauf, Terminal-History und potenziell in Agenten-Logs sichtbar.

**Massnahmen:**
- Alle verwendeten Credentials gelten als **exponiert** und sollten rotiert werden
- Passwort auf AI4Trade ändern, wenn möglich
- `.env` nach Spec-Abschluss mit frischen Credentials setzen
- **Ab sofort gelten strikte Auth-Regeln (siehe Abschnitt 11)**

---

## 2. Pfad-Policy

| Kontext | Pfad |
|----------|------|
| Lokale Entwicklung | `C:\Users\CodeLuke\ai4trade-bot` |
| VPS Runtime (später) | `/home/hermes/projects/trading/ai4trade-bot` |

**Regel:** Pfade dürfen nicht im selben Ausführungskontext gemischt werden. Die Implementierung verwendet den Entwicklungspfad. Für VPS-Deployment wird ein Deployment-Skript erstellt, das den Pfad anpasst.

---

## 3. Projektstruktur

| Kontext | Pfad |
|----------|------|
| Lokale Entwicklung | `C:\Users\CodeLuke\ai4trade-bot` |
| VPS Runtime (später) | `/home/hermes/projects/trading/ai4trade-bot` |

**Regel:** Pfade dürfen nicht im selben Ausführungskontext gemischt werden. Die Implementierung verwendet den Entwicklungspfad. Für VPS-Deployment wird ein Deployment-Skript erstellt, das den Pfad anpasst.

**Kanonischer Pfad:** `C:\Users\CodeLuke\ai4trade-bot` (Windows, lokaler Entwicklungsrechner)

```
ai4trade-bot/
├── main.py                      # Scheduler: orchestriert Trading-Loop + Heartbeat-Thread
├── config.py                    # Zentrale Konfiguration
├── .env                         # API-Keys (nicht committen) — Credentials NUR hier
├── .env.example                 # Template mit Platzhaltern (keine echten Keys)
├── .gitignore
├── requirements.txt
│
├── core/
│   ├── __init__.py
│   ├── market_data.py           # Daten-Abstraction (Binance Public API)
│   ├── technical.py             # TA-Indikatoren: RSI, MACD, EMA, Bollinger
│   ├── sentiment.py             # News holen + Claude Sentiment → Confidence-Modifier
│   ├── strategy.py              # Hybrid: TA = primär, Sentiment = Modifier, Risk = Blocker
│   └── signal_model.py          # Datenmodelle: Signal, Position, Intent
│
├── adapters/                    # Umbenannt von "platform/" — vermeidet Python-Stdlib-Konflikt
│   ├── __init__.py
│   ├── ai4trade_client.py       # Auth + Token-Refresh + generischer API-Wrapper
│   ├── heartbeat.py             # Heartbeat-Poll (eigener Thread) + Task-Verarbeitung
│   ├── signal_publisher.py      # Signale auf AI4Trade veröffentlichen
│   └── task_handler.py          # AI4Trade-Tasks entgegennehmen + routen
│
├── trading/
│   ├── __init__.py
│   ├── signal_router.py         # Signale an AI4Trade/Freqtrade/Logs weiterleiten
│   ├── risk_gate.py             # Risk-Checks: Max Position, Drawdown, Dry-Run-Default
│   └── position_state.py        # Read-Through-Cache von AI4Trade /api/positions
│
├── integrations/
│   ├── __init__.py
│   ├── freqtrade_bridge.py      # Freqtrade REST/CLI-Steuerung (optional)
│   └── primoagent_bridge.py     # PrimoAgent-Anbindung (optional)
│
├── chat/
│   ├── __init__.py
│   └── commander.py             # NL → validierter Command Intent (mode IMMER dry_run)
│
├── storage/
│   ├── events.jsonl             # Event-Log (append-only, rotation: max 10MB, 5 Dateien)
│   ├── signals.jsonl            # Signal-Historie (append-only, rotation: max 10MB, 5 Dateien)
│   └── pending_signals.jsonl    # Signal-Queue bei AI4Trade-Ausfall
│
├── tests/
│   ├── fixtures/                # Seed-Daten für Tests
│   ├── test_technical.py
│   ├── test_strategy.py
│   ├── test_risk_gate.py
│   ├── test_commander.py
│   └── test_integration.py
│
└── docs/
    └── superpowers/specs/
        └── 2026-05-07-ai4trade-bot-design.md  # Dieses Dokument
```

**Hinweis zum Paketnamen:** Das Verzeichnis heißt `adapters/` statt `platform/`, da `platform` ein Python-Standardbibliothek-Modul ist und Import-Konflikte verursachen würde.

---

## 4. Datenfluss

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│ market_data │────▶│  technical   │────▶│   strategy    │
│ (Binance)   │     │ (RSI,MACD…)  │     │ (Hybrid-Dec)  │
└─────────────┘     └──────────────┘     └───────┬───────┘
                                               │
┌─────────────┐     ┌──────────────┐           │
│  sentiment  │────▶│ Confidence   │───────────┘
│ (Claude NL) │     │  Modifier    │     Signal + Confidence
└─────────────┘     └──────────────┘           │
                                               ▼
                                        ┌──────────────┐
                                        │  risk_gate   │──── BLOCK ──▶ HOLD
                                        │ (Max Pos, DD)│
                                        └──────┬───────┘
                                               │ PASS
                                               ▼
                                        ┌──────────────┐     ┌──────────────┐
                                        │signal_router │────▶│ AI4Trade API │
                                        │              │────▶│ (simuliert)  │
                                        │              │────▶│ Freqtrade    │
                                        │              │────▶│ Event-Log    │
                                        └──────────────┘     └──────────────┘
```

### Signallebenszyklus

1. **Daten abrufen** (`core/market_data`): Krypto-Preise von Binance Public API, alle 60s
2. **TA-Berechnung** (`core/technical`): RSI, MACD, EMA-200 → rohes TA-Signal (BUY/SELL/HOLD)
3. **News abrufen** (`core/sentiment`): Krypto-News holen → Claude analysiert → Sentiment-Score (-1 bis +1)
4. **Hybrid-Entscheidung** (`core/strategy`): TA + Sentiment → Signal mit Confidence (0-100%)
5. **Risk-Gate** (`trading/risk_gate`): Max-Position-Size, Drawdown-Limit prüfen
6. **Signal-Routing** (`trading/signal_router`): Bei Pass → AI4Trade (simuliert) + Event-Log. Bei API-Fehler → Signal-Queue für Retry.

### Heartbeat (eigener Thread, alle 30s)

- AI4Trade Heartbeat pollen in separatem `threading.Thread`
- Replies, Follower, Tasks verarbeiten
- Tasks an `adapters/task_handler` weiterleiten
- Max 5 aufeinanderfolgende Polls bei `has_more_messages: true`, dann zurück zum normalen Intervall

### Chat-Kommando-Flow

```
User: "stoppe alle BTC-Positionen"
  → chat/commander.py (Claude NL → Intent)
  → {"intent": "close_positions", "pair": "BTC/USDT", "requires_approval": true, "mode": "dry_run"}
  → trading/signal_router prüft → adapters/ai4trade_client API
```

**Wichtig:** Der `mode`-Wert im Intent wird vom Commander IMMER auf `"dry_run"` gesetzt. Für MVP ist `live` out of scope. Es gibt keinen Code-Pfad, der über den Chat `"live"` setzen kann.

---

## 5. Modul-Spezifikationen

### 4.1 `core/market_data.py`

- Holt OHLCV-Daten von Binance Public API (`GET /api/v3/klines`)
- Abstrakte Schnittstelle: `get_price(symbol)`, `get_ohlcv(symbol, interval, limit)`
- Standard-Intervall: 1h, Standard-Limit: 200 Kerzen
- **Fallback:** CoinGecko (`/api/v3/simple/price`, `/api/v3/coins/{id}/ohlc`) wenn Binance nicht erreichbar
- **Retry:** Exponential Backoff (1s, 2s, 4s, max 3 Versuche), danach Fallback oder Exception

### 4.2 `core/technical.py`

- Berechnet Indikatoren auf OHLCV-Daten
- **RSI** (14-Period): Überkauft >70, Überverkauft <30
- **MACD** (12/26/9): Crossover als Signal
- **EMA** (50, 200): Golden/Death Cross
- **Bollinger Bands** (20,2): Überdehnung erkennen
- Output: `{"signal": "BUY"|"SELL"|"HOLD", "indicators": {...}, "strength": 0-100}`

### 4.3 `core/sentiment.py`

- Holt Krypto-News von kostenlosen Quellen (CryptoCompare News API)
- Sendet News-Texte an Claude API für Sentiment-Analyse
- Output: `{"score": -1.0 bis +1.0, "confidence": 0-1, "summary": "..."}`
- Update-Intervall: alle 5-15 Minuten (nicht bei jedem Tick)
- **Graceful Degradation:** Wenn Claude API nicht erreichbar → Sentiment-Score = 0 (neutral), Bot läuft mit TA-only weiter

**Known Limitation (MVP):** Sentiment ist global ("crypto"), nicht per Pair. BTC-spezifische News können sich von ETH-News unterscheiden. Für v2: `sentiment.analyze(pair)` mit pair-spezifischer News-Filterung.

### 4.4 `core/strategy.py`

- Kombiniert TA-Signal + Sentiment-Score → finales Signal
- **Confidence-Formel:** `confidence = min(100, ta_strength * (1 + sentiment_score * 0.3))`
- Schwelle: Confidence > 60 → Signal weiterleiten, sonst HOLD
- Sentiment kann nie allein ein Signal auslösen — nur TA kann BUY/SELL initiieren

### 4.5 `adapters/ai4trade_client.py`

- Wrapper um AI4Trade REST API (`https://ai4trade.ai/api`)
- Token aus `.env`
- **Token-Expiry-Handling:**
  - Bei jedem 401-Response: Bot pausiert Trading-Loop, loggt WARNING, versucht Re-Login
  - Bei Re-Login-Fehler: Bot stoppt komplett, User muss Token manuell erneuern
  - Token-Expiry wird nicht clientseitig berechnet — der Server entscheidet
- Methoden: `publish_signal()`, `get_positions()`, `follow_trader()`, `get_feed()`, `publish_strategy()`, `publish_discussion()`

### 4.6 `adapters/heartbeat.py`

- Poll-Loop in eigenem `threading.Thread`: `POST /api/claw/agents/heartbeat` alle 30s
- Verarbeitet: `discussion_reply`, `new_follower`, `discussion_mention`, `strategy_reply_accepted`, Tasks
- **`has_more_messages`-Logik:** Max 5 aufeinanderfolgende Polls bei `has_more_messages: true`, dann zurück zum normalen 30s-Intervall. Verhindert Endlosschleifen bei Server-Bugs.
- Bei wiederholten Fehlern (3x): Circuit Breaker → 60s Pause, dann Retry
- **Thread-Safety:** Schreibt nur in thread-sichere Queue, keine direkten Mutationen an geteiltem State

### 4.7 `adapters/signal_publisher.py`

- Veröffentlicht Signale über AI4Trade realtime API
- Method: `POST /api/signals/realtime`
- Fields: `market`, `action`, `symbol`, `price`, `quantity`, `executed_at`
- Bei API-Fehler: Signal wird in lokale Queue geschrieben, Retry bei nächstem Zyklus

### 4.8 `adapters/task_handler.py`

- Empfängt Tasks von Heartbeat (via thread-sichere Queue)
- Routet Tasks an passende Module (z.B. Discussion-Reply → Claude generiert Antwort)

### 4.9 `trading/signal_router.py`

- Empfängt geprüfte Signale von `risk_gate`
- Leitet weiter an: AI4Trade (simuliert), Event-Log, optional Freqtrade Bridge
- Keine eigene Order-Ausführung
- Bei AI4Trade-Fehler: Signal in Queue puffern, bei nächstem Cycle retry

### 4.10 `trading/risk_gate.py`

- **Max Position Size:** 10% des Cash pro Trade
- **Max Drawdown:** 20% vom Startkapital → alle Trades pausieren
- **Max Open Positions:** 3 gleichzeitig
- **Mode:** IMMER `dry_run` — nur simuliert auf AI4Trade. `live` ist für MVP out of scope.
- **Approval:** Jeder Trade wird geloggt

### 4.11 `trading/position_state.py`

- **Read-Through-Cache** von AI4Trade `/api/positions`
- Wird NICHT selbst geschrieben — State wird nur aus AI4Trade API-Responses gelesen
- Synchronisation: Nach jedem erfolgreichen Signal-Publish wird `/api/positions` neu geladen
- **Thread-Safety:** Zugriff nur aus Trading-Loop (Hauptthread). Heartbeat-Thread liest nicht direkt — wenn Heartbeat Positions-Daten braucht, nutzt er die Queue an den Hauptthread.

### 4.12 `integrations/freqtrade_bridge.py` (optional)

- Freqtrade REST API Steuerung
- Status-Abfrage, Pause/Resume, Signal-Weiterleitung
- Nicht im MVP-Scope — Placeholder

### 4.13 `integrations/primoagent_bridge.py` (optional)

- PrimoAgent-Anbindung
- Nicht im MVP-Scope — Placeholder

### 4.14 `chat/commander.py`

- Empfängt NL-Input → Claude erzeugt Intent-JSON
- Erlaubte Intents: `pause_pair`, `resume_pair`, `close_positions`, `show_pnl`, `follow_trader`, `status`
- Kein Intent für direktes Kaufen/Verkaufen — das macht die Strategy
- **`mode` ist IMMER `"dry_run"`** — hart codiert im Commander. `"live"` existiert als möglicher Wert im MVP nicht.
- Intent-Struktur: `{"intent": str, "pair": str, "requires_approval": bool, "mode": "dry_run"}`

---

## 6. Main Loop & Thread-Safety

### Shutdown-Mechanismus

- `threading.Event` namens `shutdown_event` ersetzt globales `running`-Flag
- Beide Threads (Trading + Heartbeat) prüfen `shutdown_event.is_set()`
- SIGINT/SIGTERM setzt `shutdown_event` → beide Threads beenden sich sauber

### Thread-Safety-Regeln

| Geteilte Ressource | Writer | Reader | Schutz |
|-------------------|--------|--------|--------|
| `position_state` Cache | Trading-Loop (nach API-Call) | Trading-Loop | Kein Lock nötig — nur ein Writer (Hauptthread) |
| Pending Signal Queue | Trading-Loop | Trading-Loop | `queue.Queue` (thread-sicher) |
| Event-Log Writer | Trading-Loop + Heartbeat-Thread | — | `logging` ist thread-sicher in Python |
| Config/Runtime Status | Nur beim Start geladen | Beide Threads | Read-Only nach Init, kein Lock nötig |
| Heartbeat → Trading Kommunikation | Heartbeat-Thread | Trading-Loop | `queue.Queue` — Tasks und Messages |

### Pseudocode

```python
import threading

shutdown_event = threading.Event()

def heartbeat_thread():
    """Eigener Thread für Heartbeat — blockiert nicht den Trading-Loop."""
    consecutive_polls = 0
    while not shutdown_event.is_set():
        try:
            messages = heartbeat.poll()
            log.info(f"Heartbeat: {len(messages)} Nachrichten")
            consecutive_polls = 0 if not messages.get("has_more_messages") else consecutive_polls + 1
            if consecutive_polls >= 5:
                consecutive_polls = 0
                shutdown_event.wait(30)
                continue
        except Exception as e:
            log.error(f"Heartbeat-Fehler: {e}")
            shutdown_event.wait(60)  # Circuit Breaker
            continue
        shutdown_event.wait(30)

# Heartbeat in eigenem Thread starten
hb = threading.Thread(target=heartbeat_thread, daemon=True, name="heartbeat")
hb.start()

# Trading-Loop (Hauptthread)
while not shutdown_event.is_set():
    try:
        ohlcv = market_data.get_ohlcv(pairs, "1h", 200)
        ta_signals = {pair: technical.analyze(ohlcv[pair]) for pair in pairs}

        if should_update_sentiment():
            try:
                sentiment = sentiment.analyze("crypto")
            except Exception:
                sentiment = {"score": 0.0, "confidence": 0.0}

        for pair, ta in ta_signals.items():
            signal = strategy.decide(ta, sentiment)
            if signal.confidence > 60:
                if risk_gate.check(signal, position_state):
                    success = signal_router.route(signal, targets=["ai4trade", "log"])
                    if success:
                        position_state.refresh()

    except Exception as e:
        log.error(f"Trading-Loop Fehler: {e}")
        shutdown_event.wait(60)

    shutdown_event.wait(cycle_interval)

# Graceful Shutdown (nach SIGINT/SIGTERM)
def graceful_shutdown(signum, frame):
    log.info("Shutdown eingeleitet...")
    shutdown_event.set()
    signal_router.flush_queue(timeout=5)
    log.info("Shutdown abgeschlossen")
```

---

## 7. Error Handling & Resilience

### Retry-Strategie

| API | Retry | Backoff | Max Versuche | Fallback |
|-----|-------|---------|-------------|----------|
| Binance | Ja | Exponential (1s, 2s, 4s) | 3 | CoinGecko |
| AI4Trade | Ja | Linear (5s, 10s, 15s) | 3 | Signal-Queue |
| Claude (Sentiment) | Ja | Exponential (1s, 2s, 4s) | 2 | Score = 0 (neutral) |
| CryptoCompare (News) | Ja | Linear (5s, 10s) | 2 | Letzter bekannter Score |

### Graceful Degradation

- **Claude API ausfall:** Sentiment-Score = 0, Bot läuft mit TA-only weiter
- **Binance ausfall:** Fallback auf CoinGecko; wenn auch CoinGecko ausfall → Trading pausieren, Heartbeat läuft weiter
- **AI4Trade ausfall:** Signale werden in lokale Queue gepuffert, bei Wiederherstellung gesendet
- **Heartbeat-Fehler:** Circuit Breaker (60s Pause), Trading-Loop läuft unabhängig weiter

### Signal-Queue

- Bei AI4Trade-API-Fehlern werden Signale in `storage/pending_signals.jsonl` gepuffert
- Max 50 Signale in der Queue, älteste werden verworfen bei Überlauf
- Retry bei jedem Trading-Cycle

---

## 8. Logging

- **Framework:** Python `logging` Module (thread-sicher)
- **Level:** Standard `INFO`, konfigurierbar über `config.py`
- **Handler:**
  - `stdout` — für Terminal-Ausgabe (Farben)
  - `RotatingFileHandler` — `storage/bot.log` (max 10MB, 5 Dateien)
- **JSONL-Dateien:** `events.jsonl` und `signals.jsonl` nutzen eigenes Rotation-Schema (max 10MB, 5 Dateien)
- **Wichtige Log-Nachrichten:**
  - `INFO`: Trade-Signal generiert, Signal auf AI4Trade veröffentlicht, Heartbeat empfangen
  - `WARNING`: API-Fallback aktiviert, Rate-Limit erreicht, Token-Expiry erkannt
  - `ERROR`: API-Ausfall nach Max-Retries, Inkonsistenter Position-State

---

## 9. Graceful Shutdown

Bei `SIGINT` / `SIGTERM`:

1. `shutdown_event.set()` — beide Threads reagieren
2. Ausstehende Signal-Queue flushen (best-effort, max 5s Timeout)
3. Letzten State in Log schreiben
4. Heartbeat-Thread beendet sich (daemon=True + shutdown_event)
5. Prozess exit mit Code 0

---

## 10. Konfiguration

| Parameter | Standardwert | Beschreibung |
|-----------|-------------|-------------|
| `AI4TRADE_TOKEN` | — | AI4Trade JWT-Token (aus `.env`) |
| `CLAUDE_API_KEY` | — | Claude API Key für Sentiment + Chat (aus `.env`) |
| `TRADING_PAIRS` | `["BTC/USDT", "ETH/USDT", "SOL/USDT"]` | Gehandelte Paare |
| `DATA_INTERVAL` | `60` | Marktdaten-Abfrage in Sekunden |
| `SENTIMENT_INTERVAL` | `300` | Sentiment-Update in Sekunden |
| `HEARTBEAT_INTERVAL` | `30` | Heartbeat-Poll in Sekunden |
| `MAX_POSITION_PCT` | `0.10` | Max 10% Cash pro Trade |
| `MAX_DRAWDOWN_PCT` | `0.20` | Max 20% Drawdown → Pause |
| `MAX_OPEN_POSITIONS` | `3` | Max gleichzeitige Positionen |
| `CONFIDENCE_THRESHOLD` | `60` | Min Confidence für Trade |
| `MODE` | `"dry_run"` | IMMER simuliert. `live` ist MVP out of scope. |
| `LOG_LEVEL` | `"INFO"` | Logging-Level |
| `MAX_SIGNAL_QUEUE` | `50` | Max gepufferte Signale bei AI4Trade-Ausfall |

---

## 11. Dependencies

| Package | Zweck |
|---------|-------|
| `requests` | HTTP-Calls (Binance, AI4Trade, CryptoCompare) |
| `pandas` | Datenverarbeitung, OHLCV |
| `python-dotenv` | `.env` Laden |
| `ta` | Technische Analyse (RSI, MACD, etc.) |
| `anthropic` | Claude API (Sentiment + Chat) |

**Dev-Dependencies:**

| Package | Zweck |
|---------|-------|
| `pytest` | Test-Runner |
| `responses` | API-Mocking für Tests |

---

## 12. Sicherheit

### Strikte Auth-Regeln

- Credentials **ausschliesslich** über `.env` — niemals in Code, Docs, Logs, Diffs, Beispielen, Test-Fixtures oder Terminal-Befehlen
- **Kein `curl`/`wget` mit Klartext-Credentials** im Terminal — stattdessen Python-Code der `.env` lädt
- `.env` in `.gitignore` — keine API-Keys im Repo
- `.env.example` enthält **nur Platzhalter**, keine echten Keys:

```
# .env.example — Platzhalter, KEINE echten Keys
AI4TRADE_TOKEN=<your-token-here>
AI4TRADE_EMAIL=<your-email-here>
AI4TRADE_PASSWORD=<your-password-here>
CLAUDE_API_KEY=<your-claude-key-here>
MODE=dry_run
```

- Auth-Tests dürfen **keine echten Credentials in Shell-Befehlen** verwenden. Bei Credential-Validierung: Environment-Variables via Python laden, alle Outputs redacten.
- Standardmäßig `dry_run` — `live` ist für MVP out of scope
- Chat-Commander setzt `mode` IMMER auf `"dry_run"` — `"live"` existiert im MVP-Code nicht als Pfad
- Risk-Gate als harter Blocker — wird nie umgangen
- Token und Login-Daten aus früherer Session als **exponiert** behandelt (Security Incident Note, Abschnitt 1)

---

## 13. Test-Strategie

### Unit-Tests (Mocked)

| Modul | Test |
|-------|------|
| `core/technical.py` | Feste OHLCV-Daten → bekannte RSI/MACD-Werte verifizieren |
| `core/strategy.py` | TA+Sentiment-Kombinationen → erwartete Confidence-Werte (inkl. min(100,...) Clamp) |
| `core/signal_model.py` | Signal-Datenmodell: Serialisierung, Validierung |
| `trading/risk_gate.py` | Position-Limits, Drawdown-Threshold, Mode-Enforcement (dry_run only) |
| `chat/commander.py` | NL-Input → Intent-JSON: mode MUSS "dry_run" sein, keine live-Intents möglich |

### Integration-Tests

| Szenario | Test |
|----------|------|
| Signal-Routing | Signal → risk_gate → signal_router → lokaler Mock-API-Server |
| Heartbeat | Heartbeat-Poll → Messages empfangen → task_handler via Queue |
| Error-Handling | Binance-Ausfall → Fallback auf CoinGecko → Graceful Degradation |
| Position-State | Mock-API-Response → Cache → Refresh → Consistency |

### Dry-Run Smoke Tests (optional)

- Gegen echte AI4Trade-Endpoints, aber nur Lesen (GET /api/signals/feed, GET /api/positions)
- Keine Schreiboperationen in automatisierten Tests
- Nur ausführbar wenn `.env` mit gültigen Credentials existiert

### Test-Stack

- `pytest` als Test-Runner
- `responses` für API-Mocking
- Lokaler Mock-API-Server für Integration-Tests
- Feste Seed-Daten in `tests/fixtures/` — **keine echten Credentials in Fixtures**

### Auth-Test-Regel

Auth-Tests dürfen **keine echten Credentials in Shell-Befehlen** verwenden. Bei Credential-Validierung: Environment-Variables via Python-Code laden (`python-dotenv`), alle Outputs in Tests redacten. Keine `curl`-Befehle mit Credentials in Test-Skripten.

---

## 14. Registrierte Daten

- **Agent ID:** 4234
- **Name:** CodeLuke Trader
- **Startkapital:** $100,000.00 (simuliert)
- **Token:** In `.env` gespeichert. Token aus früherer Session als potenziell exponiert behandelt.
