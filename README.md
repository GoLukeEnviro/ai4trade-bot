# AI4Trade Bot

**Ein modularer Signal-Generator für Krypto-Trading mit hybrider TA+AI-Sentiment-Analyse**

AI4Trade Bot ist ein Python-basierter Bot, der technische Analyse mit KI-gestützter Sentiment-Analyse kombiniert, um Handelssignale zu generieren und auf der AI4Trade-Simulated-Trading-Plattform zu veröffentlichen. Es handelt sich um einen **Signal-Adapter**, keinen Live-Trading-Executor — das System ergänzt bestehende Freqtrade/PrimoAgent-Installationen.

## Status

- **Status:** MVP (Minimum Viable Product)
- **Modus:** `dry_run` nur (simuliertes Trading mit $100k Startkapital)
- **Agent ID:** 4234
- **Python:** 3.10+

---

## Übersicht

### Was der Bot macht

AI4Trade Bot ist ein **hybrider Signal-Generator**, der:

1. **Marktdaten analysiert** — Technische Indikatoren (RSI, MACD, EMA, Bollinger Bands) von Binance/CoinGecko
2. **Sentiment analysiert** — Claude-basierte Stimmungsanalyse von Krypto-News
3. **Hybrid-Signale generiert** — Kombination aus TA und Sentiment mit Confidence-Score
4. **Auf AI4Trade veröffentlicht** — Signale werden an die AI4Trade-Simulated-Trading-Plattform gesendet
5. **Risk-Management anwendet** — Positionsgrößen, Drawdown-Limits, Max-Positions

### Was der Bot NICHT tut

- Keine direkte Order-Ausführung auf Exchanges
- Kein Live-Trading mit echtem Geld (nur Simulation)
- Kein eigenständiges Trading-System (ergänzt Freqtrade/PrimoAgent)
- Kein Backtesting (forward-only)

### Zielsetzung

- Startkapital: **$100.000** (simuliert auf AI4Trade)
- Signale für: **BTC/USDT, ETH/USDT, SOL/USDT** (konfigurierbar)
- Hybrid-Ansatz: **TA primär, Sentiment als directional Modifier**
- Ergänzung bestehender Systeme, keine Konkurrenz

---

## Architektur

### Ebenen-Modell

```
ai4trade-bot/
├── core/              → Datenmodelle + Analyse
│   ├── signal_model.py     # Frozen Dataclasses: Signal, Intent
│   ├── market_data.py      # Binance primär, CoinGecko Fallback
│   ├── technical.py        # RSI, MACD, EMA, Bollinger Bands
│   ├── sentiment.py        # Claude-basierte Sentiment-Analyse
│   └── strategy.py         # Hybrid: TA + Sentiment → Signal
│
├── adapters/          → AI4Trade API + Heartbeat
│   ├── ai4trade_client.py  # REST Client mit Bearer-Auth
│   ├── signal_publisher.py # Signal-Publish mit Queue-Fallback
│   ├── heartbeat.py        # Daemon-Thread, Circuit Breaker
│   └── task_handler.py     # Queue-Drain, Logging-Stub
│
├── trading/           → Risk + Routing
│   ├── risk_gate.py        # Positionsgröße, Drawdown, Max-Positions
│   ├── position_state.py   # Read-Through-Cache von AI4Trade
│   └── signal_router.py    # Thin Router, HOLD→nicht publizieren
│
├── chat/              → NL→Intent
│   └── commander.py        # Natural Language → Intent JSON
│
├── integrations/      → Optionale Bridges
│   ├── freqtrade_bridge.py    # Freqtrade REST/CLI (Post-MVP)
│   └── primoagent_bridge.py   # PrimoAgent (Post-MVP)
│
└── main.py            → Orchestrator (Trading-Loop + Heartbeat-Thread)
```

### Datenfluss

```
Binance/CoinGecko → MarketData → TechnicalAnalyzer → Strategy(+) → RiskGate → SignalRouter → AI4Trade
                                    ↗                    ↗
                              OHLCV-Fixture        SentimentAnalyzer → Claude API
```

### Signallebenszyklus

1. **Daten abrufen** — OHLCV von Binance (60s Intervall)
2. **TA-Berechnung** — RSI, MACD, EMA-200 → rohes TA-Signal
3. **Sentiment-Analyse** — News holen → Claude analysiert → Score [-1, 1]
4. **Hybrid-Entscheidung** — TA + Sentiment → Signal mit Confidence (0-100%)
5. **Risk-Gate** — Max-Position, Drawdown, Max-Positions prüfen
6. **Signal-Routing** — Bei Pass → AI4Trade + Event-Log, sonst HOLD

---

## Tech Stack

| Komponente | Technologie |
|-----------|-------------|
| **Sprache** | Python 3.10+ |
| **HTTP-Calls** | `requests` |
| **Datenverarbeitung** | `pandas` |
| **Technische Analyse** | `ta` (Python TA Library) |
| **Claude API** | `anthropic` |
| **Konfiguration** | `python-dotenv` |
| **Testing** | `pytest`, `responses` |

---

## Installation

### Voraussetzungen

- Python 3.10 oder höher
- pip (Python Package Installer)
- Git (optional, für Clone)

### Setup

```bash
# Repository klonen
git clone <repository-url>
cd ai4trade-bot

# Virtuelle Umgebung erstellen (empfohlen)
python -m venv venv

# Virtuelle Umgebung aktivieren
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Dependencies installieren
pip install -r requirements.txt
pip install -r requirements-dev.txt

# .env Datei konfigurieren
cp .env.example .env
# .env mit deinen Credentials editieren
```

### .env Konfiguration

Erstelle eine `.env` Datei im Projektverzeichnis:

```bash
# AI4Trade Credentials (Pflicht)
AI4TRADE_TOKEN=dein_ai4trade_token_hier
AI4TRADE_EMAIL=deine_email@example.com
AI4TRADE_PASSWORD=dein_passwort_hier

# Claude API Key (Pflicht für Sentiment)
CLAUDE_API_KEY=dein_claude_api_key_hier

# Bot-Modus (einziger unterstützter Modus)
MODE=dry_run

# Trading-Konfiguration
TRADING_PAIRS=["BTC/USDT","ETH/USDT","SOL/USDT"]
DATA_INTERVAL=60
SENTIMENT_INTERVAL=300
HEARTBEAT_INTERVAL=30

# Risk-Management
MAX_POSITION_PCT=0.10
MAX_DRAWDOWN_PCT=0.20
MAX_OPEN_POSITIONS=3
CONFIDENCE_THRESHOLD=60

# Logging
LOG_LEVEL=INFO
MAX_SIGNAL_QUEUE=50

# Claude Modell (Optional)
CLAUDE_MODEL=claude-sonnet-4-5-20250929
```

### Umgebungsvariablen erklärt

| Variable | Pflicht | Default | Beschreibung |
|----------|---------|---------|-------------|
| `AI4TRADE_TOKEN` | Ja | — | AI4Trade JWT-Token für API-Zugriff |
| `AI4TRADE_EMAIL` | Ja | — | AI4Trade Login-E-Mail |
| `AI4TRADE_PASSWORD` | Ja | — | AI4Trade Login-Passwort |
| `CLAUDE_API_KEY` | Ja | — | Anthropic API Key für Sentiment-Analyse |
| `CLAUDE_MODEL` | Nein | `claude-sonnet-4-5-20250929` | Claude Modell für Sentiment |
| `MODE` | Nein | `dry_run` | **Nur dry_run unterstützt** |
| `TRADING_PAIRS` | Nein | `["BTC/USDT","ETH/USDT","SOL/USDT"]` | Gehandelte Paare (JSON-Array) |
| `DATA_INTERVAL` | Nein | `60` | Marktdaten-Abfrage in Sekunden |
| `SENTIMENT_INTERVAL` | Nein | `300` | Sentiment-Update in Sekunden |
| `HEARTBEAT_INTERVAL` | Nein | `30` | Heartbeat-Poll in Sekunden |
| `MAX_POSITION_PCT` | Nein | `0.10` | Max 10% Cash pro Trade |
| `MAX_DRAWDOWN_PCT` | Nein | `0.20` | Max 20% Drawdown → Pause |
| `MAX_OPEN_POSITIONS` | Nein | `3` | Max gleichzeitige Positionen |
| `CONFIDENCE_THRESHOLD` | Nein | `60` | Min Confidence für Trade (0-100) |
| `LOG_LEVEL` | Nein | `INFO` | Logging-Level (DEBUG, INFO, WARNING, ERROR) |
| `MAX_SIGNAL_QUEUE` | Nein | `50` | Max gepufferte Signale bei API-Fehler |

---

## Usage

### Bot starten

```bash
python main.py
```

### Was beim Start passiert

1. **Konfiguration laden** — `.env` wird gelesen und validiert
2. **Modul-Initialisierung** — Alle Module werden initialisiert
3. **Logging gestartet** — Console + File-Logging aktiviert
4. **Heartbeat-Thread gestartet** — Daemon-Thread für AI4Trade Heartbeat
5. **Trading-Loop gestartet** — Hauptloop für Signalerzeugung

### Graceful Shutdown

- **SIGINT** (Ctrl+C) oder **SIGTERM** — Bot fährt sauber herunter
- Ausstehende Signal-Queue wird geflusht (best-effort, 5s Timeout)
- Heartbeat-Thread beendet sich
- Letzter State wird geloggt

### Log-Ausgabe

```
2026-05-07 10:00:00 INFO [main] AI4Trade Bot gestartet (Agent ID: 4234)
2026-05-07 10:00:00 INFO [main] Modus: dry_run (simuliertes Trading)
2026-05-07 10:00:00 INFO [heartbeat] Heartbeat-Thread gestartet
2026-05-07 10:00:01 INFO [market_data] OHLCV-Daten geladen: BTC/USDT, ETH/USDT, SOL/USDT
2026-05-07 10:00:01 INFO [strategy] Signal generiert: BTC/USDT BUY (Confidence: 75%)
2026-05-07 10:00:02 INFO [signal_publisher] Signal auf AI4Trade veröffentlicht: BTC/USDT BUY @ $45,234.50
```

---

## Modul-Übersicht

### `core/signal_model.py`

Frozen Dataclasses für Signal und Intent:

- **Signal**: `{"pair", "action", "price", "confidence", "mode", "timestamp"}`
- **Intent**: `{"intent", "pair", "requires_approval", "mode"}`
- **Enforcement**: `mode="dry_run"` wird in `__post_init__` erzwungen

### `core/market_data.py`

Marktdaten-Abstraktion mit Retry und Fallback:

- **Primär**: Binance Public API (`GET /api/v3/klines`)
- **Fallback**: CoinGecko API bei Binance-Ausfall
- **Retry**: Exponential Backoff (1s, 2s, 4s, max 3 Versuche)
- **Methoden**: `get_price()`, `get_ohlcv()`

### `core/technical.py`

Technische Analyse-Indikatoren:

- **RSI** (14): Überkauft >70, Überverkauft <30
- **MACD** (12/26/9): Crossover als Signal
- **EMA** (50, 200): Golden/Death Cross
- **Bollinger Bands** (20, 2): Überdehnung erkennen
- **Output**: `{"signal": "BUY"|"SELL"|"HOLD", "strength": 0-100}`

### `core/sentiment.py`

Claude-basierte Sentiment-Analyse:

- **News-Quelle**: Krypto-News von CryptoCompare
- **Analyse**: Claude API analysiert News-Texte
- **Score**: [-1, 1] (negativ bis positiv)
- **Graceful Degradation**: Bei API-Ausfall → Score = 0 (neutral)
- **Intervall**: Alle 5 Minuten (nicht bei jedem Tick)

### `core/strategy.py`

Hybrid-Strategie (TA primär, Sentiment als Modifier):

- **Confidence-Formel**: `min(100, ta_strength * (1 + sentiment_score * 0.3))`
- **Schwelle**: Confidence > 60 → Signal weiterleiten
- **Sentiment-Modifier**: Directional (positives Sentiment verstärkt BUY, negativ verstärkt SELL)
- **Regel**: Sentiment kann nie allein ein Signal auslösen

### `adapters/ai4trade_client.py`

REST Client für AI4Trade API:

- **Auth**: Bearer Token aus `.env`
- **Unwrapping**: `{success, data}` Responses
- **401-Handling**: ConnectionError bei Token-Expiry
- **Methoden**: `publish_signal()`, `get_positions()`, `follow_trader()`

### `adapters/signal_publisher.py`

Signal-Publish mit Queue-Fallback:

- **Primary**: `POST /api/signals/realtime`
- **Fallback**: In-Memory Queue bei API-Fehler
- **Separation**: `_send()` (intern) vs `publish()` (öffentlich)
- **Retry**: Bei jedem Trading-Cycle

### `adapters/heartbeat.py`

Daemon-Thread für AI4Trade Heartbeat:

- **Intervall**: Alle 30 Sekunden
- **Circuit Breaker**: 60s Pause nach 3 aufeinanderfolgenden Fehlern
- **has_more_messages-Schutz**: Max 5 aufeinanderfolgende Polls
- **Thread-Safety**: Schreibt nur in thread-sichere Queue

### `adapters/task_handler.py`

Queue-Drain für AI4Trade Tasks:

- **Aktuell**: Logging-Stub für MVP
- **Future**: Echtes Routing (publish_strategy, close_positions)
- **Queue**: Thread-sichere Queue von Heartbeat

### `trading/risk_gate.py`

Risk-Management-Gate:

- **Max Position Size**: 10% des Cash pro Trade
- **Max Drawdown**: 20% vom Startkapital → alle Trades pausieren
- **Max Open Positions**: 3 gleichzeitig
- **HOLD immer durch**: HOLD-Signale werden nie blockiert
- **0-Werte respektieren**: `is not None` statt `or`

### `trading/position_state.py`

Read-Through-Cache von AI4Trade:

- **Source**: AI4Trade `/api/positions`
- **Cache-Preserve**: Bei API-Fehler → stale-but-safe
- **Refresh**: Nach jedem erfolgreichem Signal-Publish
- **Thread-Safety**: Nur Hauptthread schreibt

### `trading/signal_router.py`

Thin Router für Signale:

- **Targets**: AI4Trade, Freqtrade (optional), Event-Log
- **HOLD-Filter**: HOLD-Signale werden nicht publiziert
- **Queue-Fallback**: Bei API-Fehler → Signal puffern
- **Flush**: Graceful Shutdown flushed Queue

### `chat/commander.py`

Natural Language → Intent:

- **Erlaubte Intents**: `pause_pair`, `resume_pair`, `close_positions`, `show_pnl`, `follow_trader`, `status`
- **Validation**: Hartes `ALLOWED_INTENTS`-Set
- **mode enforcement**: IMMER `"dry_run"` — kein Live-Path
- **Approval**: `close_positions` erfordert explizite Zustimmung

---

## Sicherheitsmodell

### 4-fach dry_run Enforcement

1. **Config Default**: `MODE=dry_run` in `.env.example`
2. **Signal.__post_init__**: Erzwingt `mode="dry_run"` bei Signal-Erstellung
3. **Intent.__post_init__**: Erzwingt `mode="dry_run"` bei Intent-Erstellung
4. **main.run() Guard**: Letzte Prüfung vor Signalausführung

### Keine Secrets in Code

- Credentials **ausschliesslich** über `.env`
- `.env` in `.gitignore`
- `.env.example` enthält nur Platzhalter
- Keine API-Keys in Code, Docs, Logs, Diffs

### Commander-Sicherheit

- **Prompt ist KEINE Sicherheitsgrenze** — hartes `ALLOWED_INTENTS`-Set
- Intent-Validation vor Ausführung
- `mode` wird IMMER auf `"dry_run"` gesetzt

### Risk-Gate-Schutz

- **HOLD immer durch** — Risk-Check wird nie umgangen
- **0-Werte respektieren** — `is not None` statt `or`
- **Max-Position, Drawdown, Max-Positions** werden hart geprüft

### Position-State-Schutz

- **Read-Through-Cache** — State wird nur aus AI4Trade gelesen
- **Cache-Preserve** — Bei API-Fehler → stale-but-safe
- **Keine eigenen Schreiboperationen** — Nur AI4Trade schreibt State

### Signal-Publisher-Schutz

- **_send()/publish()-Separation** — Verhindert Queue-Duplikation
- **Queue-Fallback** — Bei API-Fehler → Signal puffern
- **Retry** — Bei jedem Trading-Cycle

---

## Test-Suite

### Test-Statistiken

- **106 Tests** (Unit + Integration)
- **pytest** als Test-Runner
- **responses** library für HTTP-Mocking
- **unittest.mock** für Claude/Anthropic-Mocking

### Test-Kategorien

#### Unit-Tests

- `test_signal_model.py` — Signal/Intent Dataclasses, mode enforcement
- `test_market_data.py` — Binance/CoinGecko API, Retry, Fallback
- `test_technical.py` — RSI, MACD, EMA, Bollinger Bands
- `test_sentiment.py` — Claude Sentiment-Analyse, Graceful Degradation
- `test_strategy.py` — Hybrid-Strategie, TA+Sentiment-Kombination
- `test_ai4trade_client.py` — API-Client, Auth, 401-Handling
- `test_signal_publisher.py` — Publish, Queue-Fallback, Retry
- `test_heartbeat.py` — Heartbeat-Thread, Circuit Breaker
- `test_task_handler.py` — Queue-Drain, Task-Routing
- `test_risk_gate.py` — Risk-Checks, Max-Position, Drawdown
- `test_position_state.py` — Read-Through-Cache, Refresh
- `test_signal_router.py` — Routing, HOLD-Filter, Queue
- `test_commander.py` — NL→Intent, ALLOWED_INTENTS Validation

#### Integrationstests

- `test_integration.py` — Pipeline-Verdrahtung, End-to-End-Flow

### Tests ausführen

```bash
# Alle Tests
pytest

# Mit Coverage
pytest --cov=. --cov-report=html

# Spezifischer Test
pytest tests/test_strategy.py

# Mit Verbose Output
pytest -v
```

### Import-Smoke-Test

```bash
python -c "import core, adapters, trading, chat; print('✓ Alle Imports erfolgreich')"
```

---

## Design-Entscheidungen

### Was gewählt und warum

| Entscheidung | Gewählt | Warum |
|---|---|---|
| Architektur | Moduler Monolith | MVP braucht keine Microservices |
| TA-Bibliothek | ta (Python) | Leichtgewichtig, rein Python, gute Indikatoren |
| Sentiment | Claude API | Flexibel, JSON-Antworten, easy to mock |
| Marktdaten | Binance + CoinGecko | Binance primär, CoinGecko als Fallback |
| Queue | In-Memory list[dict] | MVP reicht, kein Persistenzbedarf |
| Logging | Python logging + RotatingFileHandler | Standard, zuverlässig |
| Threading | threading.Event + Queue | Genügend für MVP, kein asyncio nötig |
| Testing | pytest + responses | Standard-Stack, responses für HTTP |
| Sentiment-Modifier | Directional (asymmetrisch) | Positives Sentiment darf SELL nicht verstärken |

---

## Alternativen NICHT gewählt

### Alternative | Nicht gewählt | Grund
|---|---|---
| Live-Trading | — | MVP ist Signal-Adapter, kein Executor
| ccxt Integration | — | Kein direkter Exchange-Zugriff nötig
| WebSocket-Feeds | — | REST Polling reicht für MVP
| SQLite/JSONL-Persistenz | — | In-Memory reicht, Bot-Restart = Reset ist OK
| asyncio | — | threading reicht, kein Grund für Komplexität
| Redis Queue | — | In-Memory list reicht für MVP
| Docker/K8s | — | Lokale Ausführung reicht
| Telegram/Discord Bot | — | Chat-Commander reicht für MVP
| Backtesting-Framework | — | MVP ist forward-only
| ML-Model für Sentiment | — | Claude Prompt reicht, kein Training nötig
| Multi-Exchange | — | Binance allein reicht
| Order-Execution | — | Nur Signal-Publish, kein Order-Management
| Follow-Trader Feature | — | Endpoint nicht bestätigt, Post-MVP
| Event-Log (signals.jsonl) | — | Logging reicht für MVP
| publish_strategy()/publish_discussion() | — | Braucht bestätigte AI4Trade-Task-Formate

---

## Post-MVP Roadmap

### Near-Term (nächste Iteration)

- **Persistente Signal-Queue** (JSONL) für Bot-Restart-Sicherheit
- **Event-Log** (signals.jsonl, events.jsonl) für Analyse
- **Task-Handler echtes Routing** (publish_strategy, close_positions)
- **CoinGecko Fallback Test-Abdeckung**
- **Follow-Trader Feature** (wenn Endpoint bestätigt)

### Mid-Term

- **WebSocket-basierte Marktdaten** (Echtzeit)
- **Telegram/Discord Bot** für Remote-Control
- **Backtesting-Modus** mit historischen Daten
- **Multi-Exchange-Support** (Binance + Bybit + OKX)
- **Konfigurierbare Strategie-Plugins**

### Long-Term

- **ML-basiertes Sentiment-Modell** (trainiert statt prompted)
- **Redis/PostgreSQL** für Queue + State-Persistenz
- **Docker-Container + Health-Checks**
- **CI/CD Pipeline** (GitHub Actions)
- **Dashboard** (Grafana/Web-UI) für Monitoring
- **Paper-Trading** mit realen Marktdaten

---

## Bekannte Einschränkungen

- **Nur dry_run Modus** — Live-Trading ist nicht implementiert
- **Keine persistente Queue** — Bot-Restart = Queue-Reset
- **Sentiment-Abhängigkeit** — Claude API-Verfügbarkeit erforderlich
- **Kein Backtesting** — Forward-only Betrieb
- **Task-Handler ist Logging-Stub** — Kein echtes Routing
- **Heartbeat Circuit Breaker** — Time-basiert, nicht error-rate-basiert
- **Sentiment ist global** — Nicht pair-spezifisch (MVP)

---

## Troubleshooting

### pytest-asyncio Konflikt

**Problem**: `pytest-asyncio` Konflikt bei Test-Ausführung

**Lösung**: In `pyproject.toml`:
```toml
[tool.pytest.ini_options]
addopts = "-p no:asyncio"
```

### str.format() + JSON-Braces

**Problem**: Doppelte Klammern in Prompts für Claude

**Lösung**: Doppelte Klammern verwenden:
```python
# Falsch:
prompt = "Analyse {symbol}"  # Wird versuchen symbol zu formatieren

# Richtig:
prompt = "Analyse {{symbol}}"  # Wird als {symbol} ausgegeben
```

### RiskGate 0-Werte

**Problem**: RiskGate respektiert 0-Werte nicht

**Lösung**: `is not None` statt `or` verwenden:
```python
# Falsch:
max_pos = config.max_position or 0.1  # 0 wird zu 0.1

# Richtig:
max_pos = config.max_position if config.max_position is not None else 0.1
```

### AI4Trade 401 Error

**Problem**: `ConnectionError` bei API-Aufrufen

**Lösung**: Token in `.env` überprüfen und erneuern:
```bash
# Token neu generieren in AI4Trade Dashboard
# .env aktualisieren
AI4TRADE_TOKEN=neuer_token_hier
```

### Sentiment Score = 0

**Problem**: Sentiment ist immer neutral (0.0)

**Lösung**: Claude API Key überprüfen:
```bash
# .env überprüfen
CLAUDE_API_KEY=sk-ant-xxxxx

# API Key validieren
python -c "from anthropic import Anthropic; print(Anthropic().messages.list())"
```

### Heartbeat Circuit Breaker

**Problem**: Heartboot pausiert für 60 Sekunden

**Lösung**: Normal bei API-Fehlern, prüft AI4Trade Status:
```bash
# AI4Trade Status prüfen
curl -X POST https://ai4trade.ai/api/claw/agents/heartbeat \
  -H "Authorization: Bearer $AI4TRADE_TOKEN"
```

---

## Projektstruktur

```
ai4trade-bot/
├── main.py                      # Orchestrator (Trading-Loop + Heartbeat-Thread)
├── config.py                    # Zentrale Konfiguration
├── .env                         # API-Keys (nicht committen)
├── .env.example                 # Template mit Platzhaltern
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
│
├── core/                        # Datenmodelle + Analyse
│   ├── __init__.py
│   ├── signal_model.py          # Frozen Dataclasses: Signal, Intent
│   ├── market_data.py           # Binance + CoinGecko, Retry + Fallback
│   ├── technical.py             # RSI, MACD, EMA, Bollinger Bands
│   ├── sentiment.py             # Claude-basierte Sentiment-Analyse
│   └── strategy.py              # Hybrid: TA + Sentiment → Signal
│
├── adapters/                    # AI4Trade API + Heartbeat
│   ├── __init__.py
│   ├── ai4trade_client.py       # REST Client mit Bearer-Auth
│   ├── signal_publisher.py      # Publish mit Queue-Fallback
│   ├── heartbeat.py             # Daemon-Thread, Circuit Breaker
│   └── task_handler.py          # Queue-Drain, Logging-Stub
│
├── trading/                     # Risk + Routing
│   ├── __init__.py
│   ├── risk_gate.py             # Positionsgröße, Drawdown, Max-Positions
│   ├── position_state.py        # Read-Through-Cache von AI4Trade
│   └── signal_router.py         # Thin Router, HOLD→nicht publizieren
│
├── chat/                        # NL→Intent
│   ├── __init__.py
│   └── commander.py             # Natural Language → Intent JSON
│
├── integrations/                # Optionale Bridges
│   ├── __init__.py
│   ├── freqtrade_bridge.py      # Freqtrade REST/CLI (Post-MVP)
│   └── primoagent_bridge.py     # PrimoAgent (Post-MVP)
│
├── storage/                     # Persistenz (optional)
│   ├── events.jsonl             # Event-Log (append-only)
│   ├── signals.jsonl            # Signal-Historie (append-only)
│   └── pending_signals.jsonl    # Signal-Queue bei AI4Trade-Ausfall
│
├── tests/                       # Test-Suite
│   ├── __init__.py
│   ├── fixtures/                # Seed-Daten für Tests
│   │   └── ohlcv_fixtures.py
│   ├── test_signal_model.py
│   ├── test_market_data.py
│   ├── test_technical.py
│   ├── test_sentiment.py
│   ├── test_strategy.py
│   ├── test_ai4trade_client.py
│   ├── test_signal_publisher.py
│   ├── test_heartbeat.py
│   ├── test_task_handler.py
│   ├── test_risk_gate.py
│   ├── test_position_state.py
│   ├── test_signal_router.py
│   ├── test_commander.py
│   └── test_integration.py
│
└── docs/                        # Dokumentation
    └── superpowers/specs/
        └── 2026-05-07-ai4trade-bot-design.md
```

---

## Lizenz

MIT License — Siehe LICENSE Datei für Details.

## Contributing

Contributions sind willkommen! Bitte:

1. Fork das Repository
2. Erstelle einen Feature-Branch (`git checkout -b feature/amazing-feature`)
3. Commit deine Änderungen (`git commit -m 'feat: amazing feature'`)
4. Push zum Branch (`git push origin feature/amazing-feature`)
5. Erstelle einen Pull Request

## Support

Bei Fragen oder Problemen:

- **Issues**: GitHub Issues
- **Discord**: (Link TBD)
- **Email**: (TBD)

## Changelog

### v1.0.0 (2026-05-07)

- MVP Release
- dry_run Modus nur
- Hybrid TA+AI Sentiment Signale
- AI4Trade Integration
- 106 Tests
- Umfangreiche Dokumentation

---

**Status**: ✅ MVP Production-Ready (dry_run Modus)

**Agent ID**: 4234
**Startkapital**: $100.000 (simuliert)
**Python**: 3.10+
**Status**: Aktiv (dry_run)
