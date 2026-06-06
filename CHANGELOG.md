# Changelog

Alle wichtigen Änderungen des AI4Trade Bot Projekts werden in diesem Dokument festgehalten.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de-DE/1.0.0/),
und dieses Projekt hält sich zur semantischen Versionierung an [Semantic Versioning](https://semver.org/lang/de-DE/).

## [Unreleased]

### Added

**AI Evaluation Layer**
- `rainbow/evaluation/` Package mit DeepSeek V4 Pro Integration (6 Dateien)
- LLMEvaluator: Async LLM-Aufrufe via OpenAI-compatible API (deepseek-reasoner, timeout 5s)
- EvaluationCache: In-Memory LRU-Cache (TTL 300s, max 500 Eintraege)
- AIEvaluation-Modell: ai_confidence, risk_level, market_regime, reasoning
- Threshold-Filter: Nur Signale mit rainbow_score >= 0.5 werden evaluiert
- Graceful Degradation: Timeout/Exception → ai_evaluation = None, Signal laeuft durch
- RainbowScorer.score_and_evaluate(): Async-Methode mit asyncio.gather (score() bleibt sync)
- EvaluationConfig in Settings mit allen Parametern
- SignalStore: ai_evaluation als JSON persistiert
- 6 Evaluation-Tests (success, threshold, timeout, malformed JSON, cache hit, exception)

**Predictive Feature Pipeline**
- `core/feature_pipeline.py`: FeaturePipeline mit returns, log_returns, volatility, RSI, cyclical encoding, VWAP
- `core/predictive.py`: PredictiveEngine Wrapper (XGBoost-ready, graceful wenn kein Modell)
- Fear & Greed Index Integration via Alternative.me API
- `models/predictive/.gitkeep` fuer zukuenftige Modell-Ablage
- 8 Feature Pipeline Tests (build_features, cyclical range, empty data, fear_greed graceful, predictive graceful)

**Dokumentation**
- `docs/ai-evaluation-layer-research.md`: Forschungsbericht mit Architektur, Modellvergleich, 3-Phasen-Roadmap

### Changed
- Datenfluss: Collectors → Scorer → [AI Evaluation] → Store → Distribution
- rainbow/main.py: Scorer-Aufruf gewechselt zu score_and_evaluate()
- CryptoSignal-Modell: Neues optionales Feld ai_evaluation

### Geplant
- Live-Trading Implementierung (nach Sicherheitsaudit)
- FreqTrade Integration (PrimoDigi Bridge)
- XGBoost Modell-Training (Phase 2)
- Multi-LLM Ensemble (Phase 3)

## [0.1.0] - 2026-05-07

Erste öffentliche Version — Complete MVP mit 16 TDD-gebauten Tasks.

#### Added

**Task 1: Scaffolding** (6938e2e)
- Projekt-Struktur mit config.py, .env.example, .gitignore
- requirements.txt und requirements-dev.txt mit allen Dependencies
- Alle __init__.py Dateien für saubere Python-Module
- storage/ Verzeichnis für Logs
- Platzhalter für integrations/freqtrade_bridge.py und integrations/primoagent_bridge.py

**Task 2: Signal/Intent Datenmodelle** (a23e128)
- core/signal_model.py mit frozen dataclasses (Signal, Intent)
- __post_init__ Validierung erzwingt mode="dry_run" auf Modellebene
- tests/fixtures/ohlcv_fixtures.py mit make_ohlcv() und make_binance_ohlcv_response()
- tests/test_signal_model.py mit 6 Tests

**Task 3: Marktdaten-Abstraktion** (9c24256)
- core/market_data.py mit Binance primär und CoinGecko Fallback
- Exponential Backoff Retry-Logik (3 Versuche)
- tests/test_market_data.py mit 3 Tests
- Robuste Fehlerbehandlung mit detaillierten Fehlermeldungen

**Task 4: Technische Analyse** (c810f1e)
- core/technical.py mit RSI, MACD, EMA-50/200, Bollinger Bands
- Signal-Berechnung mit Strength-Score (0-100)
- tests/test_technical.py mit 5 Tests
- MACD-Scoring berücksichtigt Richtung (Erholung von negativ nur +5, nicht +25)

**Task 5: Sentiment-Analyse** (5c3ed7b)
- core/sentiment.py mit Claude API Integration
- Score-Clamping auf [-1, 1], Confidence auf [0, 1]
- tests/test_sentiment.py mit 6 Tests
- Fallback für ungültiges JSON und leere Headlines

**Task 6: Hybrid-Strategie** (d53c97b, ba46abf)
- core/strategy.py mit TA + Sentiment Fusion
- Richtungssichere Sentiment-Gewichtung:
  - BUY: confidence = ta_strength * (1 + sentiment_score * weight)
  - SELL: confidence = ta_strength * (1 - sentiment_score * weight)
  - HOLD: bleibt immer HOLD
- tests/test_strategy.py mit 14 Tests (7 + 7 directionale Tests)
- Konfigurierbarer sentiment_weight (Standard: 0.3)

**Task 7: AI4Trade API Client** (606a788)
- adapters/ai4trade_client.py mit requests.Session und Bearer Auth
- Duale Response-Handling ({success, data} + direktes JSON)
- HTTP 401 → ConnectionError ohne Token-Exposition
- tests/test_ai4trade_client.py mit 7 Tests
- Methoden: get_me(), publish_signal(), get_positions(), get_feed()

**Task 8: Signal Publisher** (605f6d6)
- adapters/signal_publisher.py mit In-Memory Queue
- _send()/publish() Separation verhindert Queue-Duplizierung
- FIFO Overflow Protection (max 1000 Nachrichten)
- tests/test_signal_publisher.py mit 7 Tests

**Task 9: Heartbeat Thread** (1f4520a)
- adapters/heartbeat.py mit shutdown_event.wait() statt time.sleep()
- Circuit Breaker nach 3 konsekutiven Fehlern
- has_more_messages Schutz (max 5 konsekutive Polls)
- Thread-sichere Queue für Nachrichten
- tests/test_heartbeat.py mit 7 Tests

**Task 10: Task Handler** (92bf200)
- adapters/task_handler.py mit Queue Drain (get_nowait()/queue.Empty)
- Sichere Handhabung von malformed Messages
- MVP Logging Stub, keine Trading-Aktionen
- tests/test_task_handler.py mit 7 Tests

**Task 11: Risk Gate** (e2896b3)
- trading/risk_gate.py mit Position Size, Drawdown, Max Positions Checks
- is not None statt or (erhält 0-Werte)
- HOLD passiert immer, ValueError bei starting_capital <= 0
- tests/test_risk_gate.py mit 13 Tests

**Task 12: Position State** (cf7c18c)
- trading/position_state.py mit Read-Through Cache
- Cache-Preserve bei API-Failure
- count() Methode für Position-Abfrage
- tests/test_position_state.py mit 7 Tests

**Task 13: Signal Router** (edb9652)
- trading/signal_router.py als dünner Router
- HOLD → überspringe Publish, BUY/SELL → delegiere an Publisher
- Unbekannte Targets → Warning Log, kein Crash
- flush_queue() delegiert an Publisher
- tests/test_signal_router.py mit 8 Tests

**Task 14: Chat Commander** (324e738)
- chat/commander.py mit ALLOWED_INTENTS (pause_pair, resume_pair, close_positions, show_pnl, status)
- Hard-Validierung nach Claude-Output (Prompt ist keine Sicherheitsgrenze)
- close_positions benötigt immer Bestätigung
- tests/test_commander.py mit 10 Tests

**Task 15: Main Orchestrator** (4a3035f)
- main.py mit setup_logging() (nicht auf Modulebene)
- MODE != dry_run → Reject, leeres Token → Fail Closed
- storage/ Erstellung via os.makedirs vor RotatingFileHandler
- import signal as signal_module, Variable trade_signal
- RiskGate → SignalRouter Ordering

**Task 16: Integration Tests** (eedb48a)
- tests/test_integration.py mit 6 Tests
- Full-Pipeline Test: OHLCV → TA → Strategy → RiskGate → Router → Mock Publisher
- Risk-blocked Pipeline Test
- All-Modules-Import Test
- Main Import Smoke Test

#### Changed

- Task 6: Sentiment-Modifier von richtungsunsicher zu richtungssicher
  - Alt: confidence = ta_strength * (1 + sentiment_score * weight) für alle Richtungen
  - Neu: BUY addiert, SELL subtrahiert Sentiment-Einfluss
- Task 2: pyproject.toml erstellt mit addopts="-p no:asyncio" für pytest-asyncio 0.23.2 Kompatibilität

#### Fixed

- Task 5 & 14: str.format() + JSON Curly Braces Kollision
  - Prompt-Templates verwendeten { für JSON und str.format()
  - Fix: Doppelte geschweifte Klammern {{ }} für str.format-Escaping
- Task 3: CoinGecko OHLC "low" Feld
  - Bug: p[2] statt p[3] für low-Wert
  - Fix: Korrigiert zu p[3] (high=p[1], low=p[3], close=p[4])
- Task 11: RiskGate is not None Pattern
  - Bug: or Pattern würde 0-Werte als None behandeln
  - Fix: Explizites is not None für Capital-Checks

#### Security

- 4-layer dry_run Enforcement:
  1. Signal.__post_init__ (Modellebene)
  2. RiskGate.validate() (Trading-Ebene)
  3. Main Orchestrator Start-Check (Orchestrierungsebene)
  4. .env.example MODE="dry_run" Standard (Konfigurationsebene)
- Keine Secrets in Codebase
- HTTP 401 Fehler verbergen Bearer Token
- Chat-Commander mit Hard-Validierung (Prompt ist keine Sicherheitsgrenze)

#### Build-Statistiken

- **16 Tasks** TDD-gebaut mit User-Review zwischen jedem Task
- **106 Tests** alle grün (100% Pass Rate)
- **17 Commits** (16 Tasks + 1 Bugfix für Task 6)
- **24 Pre-Build Fixes** während Plan-Review (v1→v2→v3)
- **3 Runtime Bugs** gefunden und gefixt während Build:
  - Sentiment-Direction (Task 6)
  - str.format() JSON Braces (Tasks 5, 14)
  - CoinGecko OHLC Low Field (Task 3)
- **2 MVP Simplifizierungen** dokumentiert:
  - Task Handler: Keine echten Trading-Aktionen, nur Logging
  - Heartbeat: has_more_messages Schutz statt unendliches Polling

#### Testing

- Pytest mit pytest-asyncio 0.23.2
- pytest-cov für Coverage (nicht aktiviert)
- Fixtures für OHLCV-Daten in tests/fixtures/
- Isolierte Unit-Tests für jedes Modul
- Integrationstests für Full-Pipeline
- Smoke-Tests für Imports und Main-Orchestrator

#### Documentation

- README.md mit Setup-Instructions und Architektur-Overview
- Inline-Dokumentation für alle öffentlichen APIs
- Type Hints für saubere IDE-Unterstützung
- Dieser Changelog mit vollständiger Build-Historie

---

## Hinweise zur Versionierung

- **MAJOR**: Breaking Changes, Live-Trading Aktivierung
- **MINOR**: Neue Features, backward-compatible
- **PATCH**: Bugfixes, kleinere Verbesserungen

Version 0.1.0 ist ein **Dry-Run MVP** — keine echten Trades werden ausgeführt.
