# Rainbow Intelligence Engine

Die Nervenzentrale für Krypto-Signale. Rainbow ist eine modulare Intelligenz-Schicht, die Signale aus technischer Analyse, Social Media und Nachrichten sammelt, normalisiert, bewertet und verteilt.

**Was Rainbow ist:** Eine Signal-Aggregations- und -Analyse-Engine.
**Was Rainbow nicht ist:** Kein Trading-Bot. Rainbow entscheidet nicht, sondern liefert die Datenbasis für Entscheidungen.

---

## Quickstart

```bash
# 1. Konfiguration erstellen
cp rainbow/config/rainbow.example.yml rainbow/config/rainbow.yml

# 2. Dependencies installieren
pip install -r requirements.txt

# 3. Server starten
python -m rainbow.main

> Hinweis: `main.py` ist als einfacher Legacy-Signal-Producer erhalten. Für den produktiven Betrieb und die vollständige Rainbow-Pipeline wird `python -m rainbow.main` empfohlen.

# 4. Signale abfragen
curl http://localhost:8000/signals/latest?asset=BTC&limit=10
```

---

## Architektur

Rainbow folgt dem Prinzip "Collect → Score → Distribute". Alle Collectors produzieren das gleiche Modell, alle Scores landen in der gleichen Datenbank, alle Clients erhalten die gleiche API-Schnittstelle.

### Datenfluss

```
┌─────────────────┐
│  Collectors    │  TA, Twitter, Reddit, News
└────────┬────────┘
         │ list[CryptoSignal]
         ▼
┌─────────────────┐
│ RainbowScorer   │  Gewichtung, Decay, Cross-Confirmation
└────────┬────────┘
         │ CryptoSignal mit rainbow_score (0.0-1.0)
         ▼
┌─────────────────┐
│ AI Evaluation   │  DeepSeek V4 Pro (optional, async)
└────────┬────────┘
         │ CryptoSignal + ai_evaluation (optional)
         ▼
┌─────────────────┐
│  SQLite Store  │  Persistenz, Query, Filter
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Distribution   │  REST API + Webhooks
└─────────────────┘
```

### Das CryptoSignal-Modell

**Nicht verhandelbar.** Jeder Collector produziert Listen dieses exakten Modells:

```python
class CryptoSignal(BaseModel):
    signal_id: str              # UUID
    timestamp: datetime         # UTC
    source: str                # z.B. "ta", "twitter", "reddit"
    asset: str                  # "BTC", "ETH", ...
    signal_type: SignalType    # technical, sentiment, social, news
    direction: Direction       # bullish, bearish, neutral
    strength: float             # 0.0-1.0 (Signalstaerke)
    confidence: float           # 0.0-1.0 (Zuversicht)
    value: float | None         # Optionaler Metrikenwert
    raw_data: dict | None       # Originaldaten
    metadata: dict              # Collectorspezifisch
    rainbow_score: float        # 0.0-1.0 (berechnet durch RainbowScorer)
    ai_evaluation: AIEvaluation | None  # Optional: AI-Bewertung durch DeepSeek
```

### Rainbow Score (0.0-1.0)

Der Score kombiniert alle Signale eines Assets zu einem einzigen Bewertungswert:

- **Gewichtung nach Typ**: Technical (0.4), Sentiment (0.3), Social (0.2), News (0.1)
- **Temporal Decay**: Aeltere Signale verlieren an Gewicht (Decay-Threshold: 1h)
- **Cross-Signal Confirmation**: TA bullish + Sentiment bullish = 15% Score-Boost

Beispiel: BTC mit RSI-Untenverkauft (0.8 strength) + Twitter FOMO (0.6 strength) → rainbow_score ≈ 0.75

### AI Evaluation Layer (Optional)

Das AI Evaluation Layer ist eine optionale asynchrone Stufe zwischen RainbowScorer und SignalStore. Es evaluiert Trading-Signale mit DeepSeek V4 Pro (`deepseek-reasoner`) nach qualitativen Kriterien.

**Funktionsweise:**
- **Threshold-Filter:** Nur Signale mit rainbow_score >= 0.5 werden evaluiert (geringe Latenz)
- **Asynchrone Ausführung:** LLM-Aufrufe laufen non-blocking via asyncio.gather
- **Graceful Degradation:** Timeout (5s) oder Exception → ai_evaluation bleibt None, Signal läuft normal weiter
- **In-Memory Cache:** LRU-Cache (TTL 300s, max 500 Einträge) reduziert LLM-Aufrufe

**AIEvaluation-Modell:**
```python
class AIEvaluation(BaseModel):
    ai_confidence: float      # 0.0-1.0, AI-Zuverlässigkeit
    risk_level: str           # "low", "medium", "high"
    market_regime: str        # "trending", "ranging", "volatile"
    reasoning: str            # Begründung (max 200 Zeichen)
```

**Konfiguration (rainbow.yml):**
```yaml
evaluation:
  enabled: false
  model: deepseek-reasoner
  temperature: 0.1
  timeout_seconds: 5.0
  threshold: 0.5
  cache_ttl_seconds: 300
```

---

## API

### Endpunkte

#### `GET /health`
System-Status und Collector-Health.

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "collectors": {
    "ta": "running",
    "twitter": "idle"
  },
  "uptime_seconds": 1234.5
}
```

#### `GET /signals/latest`
Neueste Signale mit Filter-Optionen.

```bash
curl "http://localhost:8000/signals/latest?asset=BTC&source=ta&limit=10"
```

Query-Parameter:
- `asset` (optional): z.B. "BTC", "ETH"
- `source` (optional): "ta", "twitter", "reddit", "news"
- `signal_type` (optional): "technical", "sentiment", "social", "news"
- `limit` (default=50, max=500): Anzahl der Ergebnisse

#### `GET /signals/{signal_id}`
Einzelnes Signal per ID.

```bash
curl http://localhost:8000/signals/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

#### `GET /metrics`
Metriken und Statistiken.

```bash
curl http://localhost:8000/metrics
```

Response:
```json
{
  "signals_stored_count": 1234,
  "collectors_active": 2,
  "collectors_total": 4
}
```

### Webhooks

#### `POST /webhooks/subscribe`
Webhook fuer Signale abonnieren mit Filterung.

```bash
curl -X POST http://localhost:8000/webhooks/subscribe \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-server.com/rainbow-webhook",
    "asset": "BTC",
    "source": "ta",
    "signal_type": "technical"
  }'
```

Response:
```json
{
  "subscription_id": "sub_abcd1234"
}
```

Filter-Optionen (alle optional):
- `asset`: Nur Signale dieses Assets
- `source`: Nur Signale dieser Quelle
- `signal_type`: Nur Signale dieses Typs

#### `GET /webhooks`
Aktive Webhooks auflisten.

```bash
curl http://localhost:8000/webhooks
```

#### `DELETE /webhooks/{sub_id}`
Webhook entfernen.

```bash
curl -X DELETE http://localhost:8000/webhooks/sub_abcd1234
```

---

## Konfiguration

Rainbow wird ueber `rainbow/config/rainbow.yml` konfiguriert.

### Beispiel-Konfiguration

```yaml
log_level: INFO
log_format: text  # text | json

db_path: rainbow/storage/signals.db

market_data:
  bitget_base_url: https://api.bitget.com
  coingecko_base_url: https://api.coingecko/api/v3
  default_interval: 1h
  default_candle_limit: 200

api:
  host: 0.0.0.0
  port: 8000

scorer:
  weights:
    technical: 0.4
    sentiment: 0.3
    social: 0.2
    news: 0.1

evaluation:
  enabled: false
  model: deepseek-reasoner
  temperature: 0.1
  timeout_seconds: 5.0
  threshold: 0.5
  cache_ttl_seconds: 300

collectors:
  ta:
    enabled: true
    interval_seconds: 60
    assets:
      - BTC
      - ETH
      - SOL
    params:
      timeframes:
        - 1h
        - 4h
```

### Collector-Konfiguration

Jeder Collector kann ein-/ausgeschaltet und konfiguriert werden:

```yaml
collectors:
  ta:
    enabled: true
    interval_seconds: 60
    assets: [BTC, ETH, SOL]
    params:
      timeframes: [1h, 4h]

  twitter:
    enabled: false  # Deaktiviert
    interval_seconds: 120
    # ... collectorspezifische Parameter
```

---

## Neuen Collector schreiben (5-Minuten-Beispiel)

Ein Collector ist eine Klasse, die von `BaseCollector` erbt und `collect()` implementiert. Das wars.

### Beispiel: Telegram Sentiment Collector

```python
# rainbow/collectors/telegram_collector.py
from rainbow.collectors.base import BaseCollector
from rainbow.models.signal import CryptoSignal, SignalType, Direction
from datetime import UTC, datetime

class TelegramCollector(BaseCollector):
    def __init__(self, bot_token: str, channels: list[str]):
        self._bot_token = bot_token
        self._channels = channels

    @property
    def name(self) -> str:
        return "telegram"

    async def collect(self) -> list[CryptoSignal]:
        signals = []
        for channel in self._channels:
            # Hier: Telegram API abrufen
            messages = await self._fetch_messages(channel)

            for msg in messages:
                signal = CryptoSignal(
                    source="telegram",
                    asset=self._extract_asset(msg.text),  # z.B. "BTC"
                    signal_type=SignalType.SOCIAL,
                    direction=self._analyze_sentiment(msg.text),
                    strength=self._calculate_strength(msg),
                    confidence=0.7,
                    metadata={"channel": channel, "msg_id": msg.id}
                )
                signals.append(signal)
        return signals

    async def _fetch_messages(self, channel: str) -> list:
        # Implementierung: Telegram Bot API
        pass

    def _extract_asset(self, text: str) -> str:
        # "$BTC" -> "BTC"
        pass

    def _analyze_sentiment(self, text: str) -> Direction:
        # Sentiment-Analyse
        pass

    def _calculate_strength(self, msg) -> float:
        # Views, Upvotes, etc.
        pass
```

### Collector registrieren

In `rainbow/main.py` den neuen Collector hinzufuegen:

```python
from rainbow.collectors.telegram_collector import TelegramCollector

telegram_collector = TelegramCollector(
    bot_token=settings.telegram_bot_token,
    channels=["@crypto_signals", "@btc_whales"]
)
engine.register_collector(telegram_collector)
```

In `rainbow.yml` konfigurieren:

```yaml
collectors:
  telegram:
    enabled: true
    interval_seconds: 180
    params:
      channels:
        - "@crypto_signals"
```

**Fertig.** Alle 3 Minuten laufen Telegram-Signale durch den Rainbow Score und landen in der API.

---

## Development Setup

```bash
# 1. Virtuelle Umgebung
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 2. Dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. Pre-Commit-Hooks (optional)
pre-commit install

# 4. Tests ausfuehren
pytest rainbow/tests/

# 5. Linting
ruff check rainbow/
ruff format rainbow/
```

### Tests ausfuehren

```bash
# Alle Tests
pytest rainbow/tests/ tests/evaluation/ tests/core/

# Spezifischer Test
pytest rainbow/tests/test_models.py -v

# Mit Coverage
pytest rainbow/tests/ tests/evaluation/ tests/core/ --cov=rainbow --cov-report=term
```

---

## Tech Stack

- **Python 3.11+**: Async-First, Type-Hints
- **FastAPI**: REST API mit automatischer OpenAPI-Doku
- **Pydantic v2**: Datenmodellierung und Validierung
- **SQLite (aiosqlite)**: Persistenz
- **pandas + ta**: Technische Analyse
- **httpx**: Async HTTP-Client

---

## Always Fresh

Rainbow ist designed fuer Speed. Alle Collectors laufen asynchron, alle APIs sind non-blocking. Signale fliessen in Echtzeit durch die Engine.

Collectors koennen hot-reloadet, Gewichte zur Laufzeit angepasst, Webhooks dynamisch subscribt werden.

Die Engine wartet nicht. Sie liefert.
