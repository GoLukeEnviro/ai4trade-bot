# Rainbow → AI4Trade Migration Plan

> Status: **In Umsetzung** · Ziel: Option B (deprecate Legacy) → Option C (entfernen)
> Stand: 2026-07-11 · ADR: `docs/decisions/ADR-2026-07-11-b2c-delivery-worker.md`
> Blocker gelöst: isolierter `rainbow/delivery/`-Worker (default `off`)

---

## Zielarchitektur (nach Migration) — ADR 2026-07-11

Phase A/B (`rainbow/adapters/` in-engine) ist **superseded**. Stattdessen:

```
┌──────────────────────────────────────────────────────────┐
│              Rainbow Engine (credential-free)            │
│  Collectors → Scorer → AI Eval → Store → REST (GET-only) │
└────────────────────────────┬─────────────────────────────┘
                             │ GET /signals/latest
                             ▼
┌──────────────────────────────────────────────────────────┐
│         rainbow/delivery/ (separater Prozess)            │
│  LocalRainbowProvider → DeliveryPolicy → SQLite Outbox   │
│  → AI4TradeClient (nur live-Mode, approval-gated)        │
│  Modi: off (default) | shadow (evidence) | live           │
└──────────────────────────────────────────────────────────┘
```

Trading-Hub advisory (#489) bleibt GET-only — kein Delivery-Worker-Pfad.

---

## Signal-Mapping: CryptoSignal → AI4Trade

### Mapping-Regeln

| AI4Trade-Feld | CryptoSignal-Quelle | Regel |
|---------------|---------------------|-------|
| `market` | `signal_type` | Immer `"crypto"` (bisherige Konvention) |
| `action` | `direction` + `strength` | `BULLISH` + strength≥0.65 → `"BUY"`, `BEARISH` + strength≥0.65 → `"SELL"`, sonst `"HOLD"` |
| `symbol` | `asset` | Direkt, ohne `/` (z.B. `"BTC"`, nicht `"BTC/USDT"`) |
| `price` | `value` oder `metadata.price` | `value` falls gesetzt, sonst `metadata["price"]`, sonst `0.0` |
| `quantity` | `metadata.position_size` | Default `0.1` falls nicht in metadata |
| `executed_at` | `time.time()` | Immer aktuell (wie Legacy) |

### HOLD-Filter-Regel

Signale mit `action="HOLD"` werden **nicht** an AI4Trade gepublisht (identisch zu Legacy `SignalRouter.route()`, der HOLD-Signale nur logged).

---

## Phasenplan

### Phase A — Adapter-Kern (`rainbow/adapters/`)

**Ziel**: AI4Trade-Client und Publisher als async Rainbow-Module.

#### A.1: `rainbow/adapters/ai4trade_client.py` — Async Client

Ersetzt `adapters/ai4trade_client.py`.

```python
class AI4TradeClient:
    """Async AI4Trade API client mit Retry und Rate-Limiting."""
    
    def __init__(self, token: str, base_url: str, timeout: float = 15.0):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=timeout,
        )
    
    async def publish_signal(self, market: str, action: str, symbol: str, 
                             price: float, quantity: float) -> dict:
        """POST /signals/realtime"""
    
    async def heartbeat(self) -> dict:
        """POST /claw/agents/heartbeat → {messages, has_more_messages}"""
    
    async def get_me(self) -> dict:
        """GET /claw/agents/me — Liveness-Check"""
    
    async def close(self) -> None:
        """Client schliessen."""
```

**Wichtig**: Kein 401-Hard-Crash mehr — stattdessen `AI4TradeAuthError` Exception, die vom Publisher abgefangen wird.

#### A.2: `rainbow/adapters/signal_mapper.py` — Signal-Übersetzer

```python
@dataclass
class AI4TradePayload:
    market: str
    action: str      # BUY, SELL, HOLD
    symbol: str
    price: float
    quantity: float
    executed_at: float

class SignalMapper:
    """CryptoSignal → AI4TradePayload (deterministisch, keine Trading-Logik)."""
    
    BUY_THRESHOLD = 0.65
    SELL_THRESHOLD = -0.65  # direction-agnostic
    
    @staticmethod
    def map(signal: CryptoSignal) -> AI4TradePayload | None:
        """None wenn HOLD (kein Publish)"""
    
    @staticmethod
    def _direction_to_action(signal: CryptoSignal) -> str:
        """BULLISH + strength≥0.65 → BUY, BEARISH + strength≥0.65 → SELL, sonst HOLD"""
```

#### A.3: `rainbow/adapters/publisher.py` — Async Publisher mit Retry-Queue

Kombiniert Legacy `SignalPublisher` + `TokenBucketRateLimiter`:

```python
class AI4TradePublisher:
    """Async Signal-Publisher mit Retry-Queue und Rate-Limiting."""
    
    def __init__(self, client: AI4TradeClient, mapper: SignalMapper,
                 max_queue: int = 50, rate_limit: float = 2.0):
        self._client = client
        self._mapper = mapper
        self._queue: asyncio.Queue[AI4TradePayload] = asyncio.Queue(maxsize=max_queue)
        self._limiter = TokenBucketRateLimiter(rate=rate_limit)  # async variant
        self._running = False
        self._task: asyncio.Task | None = None
    
    async def publish(self, signal: CryptoSignal) -> bool:
        """Sofort-Publish oder Queue bei Fehler."""
    
    async def start(self) -> None:
        """Background-Task für Queue-Processing starten."""
    
    async def stop(self) -> None:
        """Graceful shutdown — Queue leeren."""
    
    async def _process_queue(self) -> None:
        """Background-Loop: Queue leeren mit Retry."""
```

**Retry-Strategie**: Max 3 Versuche pro Signal, exponentielles Backoff (1s, 2s, 4s), danach in Dead-Letter-Log.

#### A.4: `rainbow/adapters/heartbeat.py` — Async Heartbeat

Async-Neuimplementierung von `adapters/heartbeat.py`:

```python
class AI4TradeHeartbeat:
    """Async Heartbeat mit Circuit-Breaker und Task-Message-Polling."""
    
    MAX_CONSECUTIVE_POLLS = 5
    CIRCUIT_BREAKER_THRESHOLD = 3
    
    def __init__(self, client: AI4TradeClient, message_queue: asyncio.Queue,
                 interval: int = 30, cb_pause: int = 60):
        ...
    
    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Endlosschleife bis shutdown."""
    
    async def stop(self) -> None:
        """Graceful stop."""
```

#### A.5: `rainbow/adapters/task_handler.py` — Async Task Handler

Async-Neuimplementierung von `adapters/task_handler.py`:

```python
class AI4TradeTaskHandler:
    """Verarbeitet eingehende Task-Messages vom Heartbeat."""
    
    def __init__(self, message_queue: asyncio.Queue):
        self._queue = message_queue
    
    async def process_pending(self) -> int:
        """Alle Messages aus Queue verarbeiten, Anzahl zurueckgeben."""
```

### Phase B — Rainbow-Integration & Feature-Flag

#### B.1: `rainbow/config/settings.py` — AI4Trade-Konfiguration

```python
class AI4TradeConfig(BaseModel):
    enabled: bool = False                       # Feature-Flag (off by default!)
    token: str = ""                             # AI4TRADE_TOKEN
    base_url: str = "https://ai4trade.ai/api"
    rate_limit: float = 2.0                     # Requests/sec
    max_queue: int = 50
    publish_threshold: float = 0.5              # rainbow_score >= threshold → publish
    heartbeat_enabled: bool = False
    heartbeat_interval: int = 30
```

In `RainbowSettings` integrieren:

```yaml
# rainbow/config/rainbow.yml (neu)
ai4trade:
  enabled: false
  token: "${AI4TRADE_TOKEN}"
  base_url: "https://ai4trade.ai/api"
  rate_limit: 2.0
  max_queue: 50
  publish_threshold: 0.5
  heartbeat_enabled: false
  heartbeat_interval: 30
```

#### B.2: `rainbow/main.py` — Adapter-Startup/Shutdown

In `RainbowEngine.initialize()`:

```python
if self.settings.ai4trade.enabled:
    self._ai4trade_client = AI4TradeClient(
        token=self.settings.ai4trade.token,
        base_url=self.settings.ai4trade.base_url,
    )
    self._signal_mapper = SignalMapper()
    self._publisher = AI4TradePublisher(
        client=self._ai4trade_client,
        mapper=self._signal_mapper,
        max_queue=self.settings.ai4trade.max_queue,
        rate_limit=self.settings.ai4trade.rate_limit,
    )
    await self._publisher.start()
    
    if self.settings.ai4trade.heartbeat_enabled:
        self._ai4trade_mq: asyncio.Queue = asyncio.Queue()
        self._heartbeat = AI4TradeHeartbeat(
            client=self._ai4trade_client,
            message_queue=self._ai4trade_mq,
            interval=self.settings.ai4trade.heartbeat_interval,
        )
        self._task_handler = AI4TradeTaskHandler(message_queue=self._ai4trade_mq)
```

In `_run_collector_loop()` — nach dem Scoren:

```python
if publisher and scored:
    for sig in scored:
        if (sig.rainbow_score or 0.0) >= publish_threshold:
            await publisher.publish(sig)
```

### Phase C — Contract Tests

#### C.1: `tests/rainbow/adapters/test_signal_mapper.py`

```python
class TestSignalMapper:
    """Contract: deterministisches Mapping CryptoSignal → AI4TradePayload."""
    
    def test_bullish_strong_signal_maps_to_buy(self):
        """BULLISH + strength=0.8 → BUY"""
    
    def test_bearish_strong_signal_maps_to_sell(self):
        """BEARISH + strength=0.8 → SELL"""
    
    def test_weak_signal_maps_to_hold(self):
        """BULLISH + strength=0.4 → HOLD (unter Threshold)"""
    
    def test_hold_is_never_published(self):
        """mapper.map() returns None für HOLD"""
    
    def test_neutral_direction_defaults_to_hold(self):
        """Direction.NEUTRAL → HOLD"""
    
    def test_asset_strips_slash(self):
        """'BTC/USDT' → symbol='BTC' (Legacy-Kompatibilität)"""
    
    def test_price_falls_back_to_metadata(self):
        """value=None, metadata.price=50000 → price=50000"""
    
    def test_quantity_default(self):
        """metadata ohne position_size → quantity=0.1"""
```

#### C.2: `tests/rainbow/adapters/test_publisher.py`

```python
class TestAI4TradePublisher:
    """Contract: Queue-Verhalten identisch zu Legacy SignalPublisher."""
    
    async def test_publish_success_returns_true(self): ...
    async def test_publish_failure_enqueues(self): ...
    async def test_queue_flush_on_shutdown(self): ...
    async def test_queue_overflow_drops_oldest(self): ...
    async def test_rate_limiter_prevents_burst(self): ...
    
    class TestAgainstLegacyBehavior:
        """Cross-check: Neuer Publisher verhält sich wie alter."""
        
        async def test_identical_retry_behavior(self): ...
        async def test_max_queue_overflow_identical(self): ...
```

#### C.3: `tests/rainbow/adapters/test_ai4trade_client.py`

```python
class TestAI4TradeClient:
    """HTTP-level: korrekte Payload, Auth-Header, Error-Handling."""
    
    async def test_publish_signal_payload_shape(self):
        """Gesendetes JSON entspricht Legacy paylaod."""
    
    async def test_401_raises_auth_error(self):
        """Kein Hard-Crash, sondern spezifische Exception."""
```

### Phase D — Docker/Compose-Migration (nach Canary)

**Voraussetzung**: Adapter läuft ≥ 1 Woche im Canary-Betrieb ohne Fehler.

#### D.1: `docker-compose.yml` — Bot in Legacy-Profil verschieben

```yaml
# bot-Service aus default entfernen, in legacy-Profil:
services:
  bot:
    profiles: ["legacy"]  # ← neu
    build: .
    ...

  rainbow:
    # bleibt im default, KEIN Profil
    ...

  prometheus:
    depends_on:
      rainbow:           # ← war: bot
        condition: service_healthy
```

#### D.2: `monitoring/prometheus.yml` — Scrape-Targets aktualisieren

```yaml
scrape_configs:
  - job_name: "ai4trade-bot"
    static_configs:
      - targets: ["rainbow:8000"]    # ← war: bot:9090
    metrics_path: "/metrics/prometheus"
```

#### D.3: `rainbow.Dockerfile` — Adapter-Abhängigkeiten

Falls `rainbow/adapters/` neue Dependencies braucht (httpx ist bereits in requirements.txt).

### Phase E — Option C: Legacy Cleanup (separater PR)

**Voraussetzung**: Phase D deployed + 2 Wochen Betrieb ohne Legacy-Bot.

| Komponente | Aktion |
|------------|--------|
| `main.py` | Löschen |
| `core/technical.py` | Löschen (→ `ta_collector.py`) |
| `core/strategy.py` | Löschen (→ `RainbowScorer`) |
| `core/market_data.py` | Löschen (→ `rainbow/market_data/`) |
| `core/sentiment.py` + `ai/sentiment.py` | `core/sentiment.py` löschen, `ai/sentiment.py` evaluieren |
| `core/signal_model.py` | Auf `Signal` + `Intent` prüfen, beide löschen falls Rainbow-only |
| `core/feature_pipeline.py` | Evaluieren: braucht Rainbow es? Wenn nein → löschen |
| `core/predictive.py` | Wie feature_pipeline |
| `adapters/` (Legacy) | Komplett löschen |
| `trading/signal_router.py` | Löschen |
| `storage/` (Legacy) | `sqlite_repository.py` + `repository.py` löschen |
| `chat/commander.py` + `tests/test_commander.py` | Löschen (Referenzen auf tote Trading-Features) |
| `exchanges/` | Evaluieren: braucht Rainbow es? |
| `Dockerfile` (Legacy) | Löschen |
| `config.py` | Auf Rainbow-only reduzieren |
| `requirements.txt` | Legacy-only Pakete entfernen |

---

## Akzeptanzkriterien (pro Phase)

### Phase A + B (Adapter-Implementierung)
- [ ] `ruff check rainbow/adapters/` — clean (E, F, I, W)
- [ ] `ruff format rainbow/adapters/` — clean
- [ ] `python -c "from rainbow.adapters.ai4trade_client import AI4TradeClient"` — importierbar
- [ ] `python -c "from rainbow.adapters.signal_mapper import SignalMapper"` — importierbar
- [ ] Adapter **nicht** im Default-Compose aktiv (feature-flag `enabled: false`)
- [ ] `rainbow/main.py` Startup bricht nicht ab, wenn Adapter deaktiviert oder Token fehlt

### Phase C (Contract Tests)
- [ ] `pytest tests/rainbow/adapters/ -v` — alle grün
- [ ] `pytest tests/ -v` — kein bestehender Test gebrochen
- [ ] SignalMapper: identisches Payload zu Legacy `SignalPublisher._send()`
- [ ] Publisher: identisches Retry/Queue-Verhalten zu Legacy `SignalPublisher`

### Phase D (Deployment)
- [ ] `docker compose up -d` startet Rainbow + Prometheus, **nicht** Legacy-Bot
- [ ] `docker compose --profile legacy up -d bot` startet Legacy-Bot (Rollback getestet)
- [ ] Prometheus scraped `rainbow:8000/metrics/prometheus`
- [ ] Rainbow Healthcheck via `/health` funktioniert

### Phase E (Option C Cleanup)
- [ ] `ruff check .` — clean
- [ ] `ruff format --check .` — clean
- [ ] `pytest tests/ -v --ignore=tests/legacy/` — alle grün
- [ ] `python -m rainbow.main` — startet ohne Legacy-Import-Fehler
- [ ] Keine Referenzen auf `core.technical`, `core.strategy`, `core.market_data`, `adapters.*` mehr im Repo

---

## Risiken & Mitigation

| Risiko | Wahrscheinlichkeit | Mitigation |
|--------|-------------------|------------|
| AI4Trade-API ändert Payload-Format | Niedrig | Contract-Tests (Phase C) dokumentieren erwartetes Format. API-Änderung → Mapper-Update. |
| Adapter-Token läuft ab (401) | Mittel | `AI4TradeAuthError` Exception + Graceful Degradation (Publisher stoppt, Rainbow läuft weiter). Heartbeat erkennt Auth-Fehler früh. |
| Rate-Limit-Verletzung bei Volatilität | Mittel | Token-Bucket-Rate-Limiter (2 req/s default, konfigurierbar). Queue puffert Bursts. |
| `rainbow/main.py` hat null Tests (Refactor-Risiko) | Hoch | Charakterisierungstests **vor** Phase B.2 schreiben. Nur minimale Änderungen an bestehender Loop. |
| Legacy-Docker-Compose-Änderung bricht VPS-Deployment | Niedrig | `profiles: ["legacy"]` erhält alten Pfad, `--profile legacy` getestet vor Merge. |

---

## Sequenzierung & Abhängigkeiten

```
Phase A (Adapter-Kern)          ← kein Risiko, unabhängig
  │
  ├─► Phase C (Contract Tests)  ← parallel nach A.2/A.3
  │
  ├─► Phase B (Integration)     ← nach A vollständig
  │
  └─► Charakterisierungstests   ← VOR B.2 (rainbow/main.py)
       für rainbow/main.py

Phase D (Deployment)            ← nach B + C + 1 Woche Canary
  │
  └─► Phase E (Option C)        ← nach D + 2 Wochen Betrieb
```

**Geschätzter Aufwand**:
- Phase A: 3–4 Std (4 neue Dateien, ~200–300 LOC)
- Phase B: 1–2 Std (Config + Wiring in rainbow/main.py)
- Phase C: 1.5–2 Std (3 Testdateien)
- Charakterisierungstests: 1 Std
- Phase D: 30 Min (Config-Änderungen)
- Phase E: 1 Std (Bulk-Delete + Verifikation)

**Gesamt: ~9 Std** (exkl. Canary-Wartezeit)

---

## Entscheidungspunkte (vor Phase A zu klären)

1. **AI4TRADE_TOKEN**: Wird es pro Umgebung in `rainbow/config/rainbow.yml` oder via `.env` gesetzt? Aktuell liest `config.py` es via `SecretProvider`. Vorschlag: Rainbow-Settings lesen Token aus `os.environ["AI4TRADE_TOKEN"]` — identisch zu Legacy, aber ohne `SecretProvider`-Abhängigkeit.

2. **publish_threshold**: Legacy nutzt `CONFIDENCE_THRESHOLD=60` (100er-Skala). Rainbow hat `rainbow_score` auf 0.0–1.0. Default 0.5 entspricht etwa dem Legacy-60%-Threshold. Soll der Threshold konfigurierbar sein? → Ja, in `ai4trade.publish_threshold`.

3. **Task-Handler-Semantik**: Legacy `TaskHandler` loggt nur Tasks und zählt sie. Soll die Rainbow-Version gleich simpel sein, oder soll sie echte Task-Verarbeitung bekommen? → Phase A implementiert identische Semantik (log + count). Echte Task-Verarbeitung ist separater Scope.
