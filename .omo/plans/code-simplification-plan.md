# Code-Simplification-Plan — ai4trade-bot

> Stand: 2026-07-10 · Codebase: v0.2.0 · Zustand: **Transitional** (Legacy `main.py`+`core/` parallel zu `rainbow/`)

---

## Projekt-Diagnose

Das Projekt hat **zwei parallele Architekturen**, die nach einem Refactor ("simplify to pure signal framework") entstanden sind:

| Schicht | Legacy (`main.py` + `core/`) | Rainbow (`rainbow/`) |
|---------|------------------------------|---------------------|
| Orchestrierung | `main.py` (180 Z., threaded) | `rainbow/main.py` (304 Z., async) |
| Marktdaten | `core/market_data.py` (sync, requests) | `rainbow/market_data/bitget.py` (async, httpx) |
| TA-Analyse | `core/technical.py` (89 Z., magic numbers) | `rainbow/collectors/ta_collector.py` (211 Z., Konstanten) |
| Sentiment | `core/sentiment.py` → `ai/sentiment.py` (LLM) | `rainbow/collectors/{twitter,reddit,news}_collector.py` ( regelbasiert) |
| Scoring | `core/strategy.py` (51 Z., simple) | `rainbow/processor/scorer.py` (129 Z., gewichtet+decay) |
| Persistenz | `storage/sqlite_repository.py` (sync) | `rainbow/processor/store.py` (async) |
| Signalmodell | `core/signal_model.py` (`Signal` dataclass) | `rainbow/models/signal.py` (`CryptoSignal` pydantic) |

**README sagt**: Rainbow ist der empfohlene Pfad, `main.py` ist "Legacy-Signal-Producer".

**Echte Logik-Dopplung**: TA-Scoring (fast identisch), Market-Data-Fetch (gleiche API, gleiche Normalisierung).
**Konzeptionelle Überschneidung**: Sentiment, Strategy/Scorer, Storage, Orchestrierung — verschiedene Zwecke, gleiche Domäne.

---

## Phase 1: Dead Code Removal (Low Risk · Quick Wins)

### 1.1 `chat/commander.py` — VOLLSTÄNDIG DEAD
- **Problem**: Referenziert entfernte Trading-Intents (`close_positions`, `toggle_shadow_mode`, `set_risk_level`, `show_pnl`). Diese Features wurden im Refactor gelöscht.
- **Evidence**: Weder `main.py` noch `rainbow/main.py` importieren `Commander`. Alle Intents beziehen sich auf gelöschte Execution-Layer.
- **Aktion**: Ganze Datei löschen + `chat/` Verzeichnis entfernen.
- **Aufwand**: 5 Min

### 1.2 `Intent` class in `core/signal_model.py` — DEAD (nur von commander.py genutzt)
- **Problem**: `Intent` dataclass wird nur von `chat/commander.py` importiert. Wenn Commander weg → Intent weg.
- **Aktion**: `Intent` class entfernen. `Signal` class behalten (noch von Legacy `main.py` genutzt).
- **Aufwand**: 5 Min

### 1.3 `core/market_data.py` `_parse_timestamp()` — DEAD WRAPPER
- **Problem**: Zeile 79-81: `_parse_timestamp` ruft nur `_normalize_timestamp` auf — 100% redundanter Wrapper.
- **Aktion**: Methode löschen, ggf. Callsite-Referenzen prüfen.
- **Aufwand**: 5 Min

### 1.4 `rainbow/main.py` `_engine` Global — DEAD VARIABLE
- **Problem**: Zeile 33: `_engine: RainbowEngine | None = None` — wird deklariert aber nirgendwo zugewiesen oder gelesen. Die Engine wird in `create_engine()` lokal erstellt und über `lifespan` an `api_module._engine` übergeben.
- **Aktion**: Zeile löschen.
- **Aufwand**: 2 Min

### 1.5 `core/sentiment.py` — OVER-ENGINEERED PROXY SHIM
- **Problem**: 19-Zeilen Modul, das `ai/sentiment.py` re-exportiert und dann dessen `create_provider` durch eine Proxy-Funktion ersetzt (damit Tests `core.sentiment.create_provider` patchen können). Die Indirektion macht den Codefluss schwer nachvollziehbar.
- **Aktion**: `main.py` direkt `from ai.sentiment import SentimentAnalyzer` importieren lassen. `core/sentiment.py` löschen. Tests anpassen, sodass sie `ai.sentiment.create_provider` patchen.
- **Aufwand**: 20 Min (inkl. Test-Anpassung)

### 1.6 Unbenutzte Imports — Ruff-gesteuert
- **Aktion**: `ruff check --select F401` über gesamten Source-Tree laufen lassen. Gefundene Unused Imports entfernen.
- **Aufwand**: 10 Min

**Phase 1 Gesamt: ~45 Min · Zero Behavior Change**

---

## Phase 2: Duplicate Code Elimination (Medium Risk)

### 2.1 TA-Scoring: `core/technical.py` ↔ `rainbow/collectors/ta_collector.py`
- **Problem**: BEIDE implementieren identische TA-Logik mit denselben Indikatoren (RSI 14, MACD 12/26/9, EMA 50/200, Bollinger 20/2) und nahezu identischen Scoring-Regeln:
  - RSI < 30 → +30, RSI > 70 → -30, etc.
  - MACD > 0 + hist > 0 → +25, etc.
  - EMA strong bull → +20, etc.
  - Bollinger lower → +15, etc.
  - Base = 50, BUY > 65, SELL < 35
- **Legacy** nutzt Magic Numbers inline; **Rainbow** nutzt benannte Konstanten.
- **Lösung**: Shared TA-Scoring-Modul `core/ta_scoring.py` (oder `rainbow/collectors/ta_scoring.py`) mit Konstanten + Score-Funktion extrahieren. Beide Consumer nutzen das gemeinsame Modul.
- **Aufwand**: 45 Min

### 2.2 Market-Data-Normalisierung: Timestamp-Logik
- **Problem**: `_normalize_timestamp()` existiert in `core/market_data.py` (Zeile 64-77) mit identischer Logik zu `core/market_signals.py` `_latest_timestamp()` (Zeile 88-102) — beide behandeln ms/s-Erkennung, `>1e11` Schwellenwert, etc.
- **Lösung**: Gemeinsame `core/timestamp_utils.py` mit `normalize_epoch_timestamp(value: float) -> float | None`.
- **Aufwand**: 20 Min

### 2.3 `feature_pipeline.py` Stunde/Tag-Muster wiederholt
- **Problem**: Zeile 40-48 (hour) und 53-58 (day_of_week) sind strukturell identisch — beide prüfen DatetimeIndex → timestamp-Spalte → Fallback 0.
- **Lösung**: Helper `_extract_time_component(df, attr: str) -> pd.Series` extrahieren, beide Aufrufe konsolidieren.
- **Aufwand**: 15 Min

### 2.4 Sentiment-Heuristik in 3 Collectoren dupliziert
- **Problem**: `twitter_collector.py`, `reddit_collector.py`, `news_collector.py` implementieren alle die gleiche Keyword-Matching-Heuristik: bullish/bearish Wortlisten → direction + strength.
- **Lösung**: Gemeinsames `rainbow/collectors/sentiment_keywords.py` mit `score_text_sentiment(text: str) -> tuple[Direction, float]` extrahieren. Alle 3 Collectoren rufen dieses Shared Modul auf.
- **Aufwand**: 40 Min

**Phase 2 Gesamt: ~2 Std · Behavior-Preserving Refactoring**

---

## Phase 3: Complexity Reduction (Medium Risk)

### 3.1 `rainbow/main.py` `_build_collectors()` — 57-Zeilen if/elif-Kette
- **Problem**: Lines 87-143: 4-Branch if/elif für Collector-Typen (ta/twitter/reddit/news). Jeder Branch instanziiert unterschiedlich, mit unterschiedlichem Error-Handling.
- **Lösung**: Registry-Pattern: `_COLLECTOR_FACTORIES: dict[str, Callable]` als Modul-Konstante. `_build_collectors()` iteriert und dispatcht.
- **Aufwand**: 40 Min

### 3.2 `rainbow/main.py` Kapselungsbrüche
- **Problem**: Mehrere direkte Zugriffe auf private Attribute anderer Module:
  - Line 58: `api_module._webhook_manager = self.webhooks`
  - Line 76-77: `self.scorer._evaluator = evaluator` / `self.scorer._evaluation_threshold = ...`
  - Line 140: `api_module._collector_status[name] = "running"`
  - Line 183-184: `api_module._collector_status[name] = "stopped"`
  - Line 264-266: `api_module._store = engine.store` etc.
- **Lösung**:
  - Scorer bekommt eine public `set_evaluator(evaluator, threshold)` Methode
  - `api_module` bekommt einen `EngineState` dataclass/dict als öffentliche API statt private Attribute
- **Aufwand**: 30 Min

### 3.3 `rainbow/main.py` `_run_collector_loop()` — tiefe Verschachtelung
- **Problem**: 50-Zeilen Funktion mit 3 Ebenen Verschachtelung (while → try → for → if → try), Metrics-Instrumentierung vermischt mit Business-Logik.
- **Lösung**: In `_process_collector_batch(collector, scorer, store, webhooks)` und `_dispatch_webhooks(webhooks, signals)` aufteilen. Metrics bleiben in den Helpern, aber die Loop-Funktion wird lesbar.
- **Aufwand**: 30 Min

### 3.4 `rainbow/main.py` `_init_evaluator()` — Exzessives getattr()
- **Problem**: Lines 62-85: 5x `getattr(evaluation_cfg, ...)` für Attribute, die das Settings-Objekt direkt typsicher exponieren sollte.
- **Lösung**: `RainbowSettings` so erweitern, dass `evaluation` ein getyptes Pydantic-Modell ist (kein optionalales Attribut mehr). Dann direkter Zugriff: `evaluation_cfg.model` statt `getattr(evaluation_cfg, "model", "deepseek-reasoner")`.
- **Aufwand**: 25 Min

### 3.5 `core/technical.py` Zeile 71 — Nested Ternary
- **Problem**: `signal = "BUY" if strength > 65 else ("SELL" if strength < 35 else "HOLD")` — nested ternary, verstößt gegen Code-Standard.
- **Lösung**: if/elif/else Kette oder `ta_collector._direction_label()` aus 2.1 nutzen.
- **Aufwand**: 5 Min (in 2.1 enthalten)

### 3.6 `rainbow/evaluation/llm_evaluator.py` `evaluate()` — 55-Zeilen Monolith
- **Problem**: Promptbau, API-Call, Response-Parsing, Cache, Logging, Error-Handling alle in einer Methode.
- **Lösung**: Aufteilen in `_build_prompt(signal)`, `_call_llm(prompt)`, `_parse_response(raw, latency_ms)`. `evaluate()` orchestriert nur.
- **Aufwand**: 30 Min

**Phase 3 Gesamt: ~2.5 Std**

---

## Phase 4: Code-Quality-Hygiene (Low Risk)

### 4.1 `core/technical.py` Magic Numbers → Konstanten
- **Problem**: Alle Thresholds sind inline Magic Numbers (30, 45, 55, 70, 25, 10, 20, 15).
- **Lösung**: Modulkonstanten wie in `ta_collector.py` (`RSI_OVERSOLD = 30`, etc.). Wird durch 2.1 obsolet, falls shared Modul erstellt wird.
- **Aufwand**: entfällt bei 2.1

### 4.2 `llm_evaluator.py` Zeile 63 — KeyError-Gefahr
- **Problem**: `os.environ["DEEPSEEK_API_KEY"]` — wirft `KeyError` wenn Env-Var fehlt, ohne klare Fehlermeldung.
- **Lösung**: `os.getenv("DEEPSEEK_API_KEY")` + expliziter Check mit `raise ConfigurationError("DEEPSEEK_API_KEY nicht gesetzt")`.
- **Aufwand**: 10 Min

### 4.3 `core/feature_pipeline.py` unused import `math`
- **Problem**: Zeile 4: `import math` — wird nirgendwo im Modul verwendet.
- **Lösung**: Import entfernen (wird durch 1.6 Ruff-Lauf erfasst).
- **Aufwand**: 1 Min

### 4.4 `rainbow/main.py` unused imports
- **Problem**: `import os` (Line 5) und `from typing import Any` (Line 8) — beide ungenutzt im Modul.
- **Lösung**: Entfernen (wird durch 1.6 Ruff-Lauf erfasst).
- **Aufwand**: 1 Min

**Phase 4 Gesamt: ~15 Min**

---

## Priorisierung & Reihenfolge

| Phase | Aufwand | Risk | Impact | Wann? |
|-------|---------|------|--------|-------|
| **1 — Dead Code** | ~45 Min | Zero | Aufräumen, Klarheit | **Sofort** |
| **4 — Hygiene** | ~15 Min | Minimal | Ruff-Clean, Lint-Pass | **Nach Phase 1** |
| **2 — Deduplikation** | ~2 Std | Medium | Wartbarkeit, DRY | **Nach 1+4** |
| **3 — Complexity** | ~2.5 Std | Medium | Lesbarkeit, Erweiterbarkeit | **Nach Phase 2** |

**Gesamtaufwand: ~5.5 Std**

---

## Offene Architektur-Entscheidung (User-Input nötig)

Die größte strategische Frage ist: **Soll die Legacy-Architektur (`main.py` + `core/`) aktiv erhalten oder als deprecated markiert und langfristig zugunsten von Rainbow entfernt werden?**

| Option | Implikation |
|--------|------------|
| **A) Legacy behalten** | Deduplikation (Phase 2.1) zwingend. Zwei Pipelines warten. Höherer Wartungsaufwand. |
| **B) Legacy → deprecated** | `main.py` als "not recommended" markieren. Phase 2.1 Fokus auf Rainbow. Legacy nur Bugfixes. |
| **C) Legacy entfernen** | `main.py`, `core/technical.py`, `core/market_data.py`, `core/strategy.py`, `storage/sqlite_repository.py`, `adapters/`, `trading/signal_router.py` alle löschen. Rainbow wird einzige Pipeline. Größter Cleanup, aber Breaking Change für AI4Trade-Integration. |

Diese Entscheidung bestimmt den Scope von Phase 2 maßgeblich. Vor Start Klarheit einholen.

---

## Verifikations-Strategie

Nach jeder Phase:
1. `ruff check .` — Lint clean
2. `ruff format --check .` — Format clean
3. `pytest rainbow/tests/ tests/core/ tests/evaluation/ -v` — Alle Tests grün
4. `python -c "from main import run; from rainbow.main import main"` — Beide Entrypoints importierbar
5. Diff-Review: Behavior-Unterschiede dokumentieren
