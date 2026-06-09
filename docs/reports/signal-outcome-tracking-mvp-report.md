# Signal Outcome Tracking MVP — Implementation Report

**Issue:** #32 — feat: Signal outcome tracking for self-improvement feedback loop  
**Branch:** `feature/signal-outcome-tracking`  
**Commit:** `c227102`  
**Date:** 2026-06-09

---

## Verdict: 🟢 GREEN — Healthscore: 92/100

## Implemented Scope

### 1. Outcome Model (`core/outcomes/model.py`)
- `OutcomeLabel` enum: `win`, `loss`, `neutral`, `expired`, `unknown`
- `SignalOutcome` Pydantic model with all required fields:
  - signal_id, asset, direction, signal_class, source
  - emitted_at, evaluated_at, evaluation_window_seconds
  - entry_price, outcome_price, price_change_pct
  - expected_direction, outcome_label, outcome_score
  - reason, confidence_at_signal, extra
- Safety validator enforces observational-only nature

### 2. Outcome Repository (`core/outcomes/repository.py`)
- Dedicated SQLite database (`storage/outcomes.db`)
- `signal_outcomes` table with proper indexing (asset, label, emitted_at)
- CRUD: insert, upsert (idempotent), get_by_signal_id, query (with filters), count, export_all
- WAL mode for concurrent safety
- No interference with existing canonical_signals.db

### 3. Price Provider Abstraction (`core/outcomes/price_provider.py`)
- `PriceProvider` protocol: `get_price(asset, at_time) -> float | None`
- `StaticPriceProvider`: fixed price map for testing
- `CallbackPriceProvider`: delegate to callable for flexible test scenarios
- No exchange credentials required

### 4. Outcome Evaluator (`core/outcomes/evaluator.py`)
- `OutcomeEvaluator`: deterministic signal → outcome classification
- Bullish signal: WIN if price up ≥ threshold, LOSS if down ≥ threshold
- Bearish signal: WIN if price down ≥ threshold, LOSS if up ≥ threshold
- Neutral/unknown direction: always NEUTRAL
- Missing price data: graceful UNKNOWN with reason code
- Idempotent: skips signals that already have outcomes
- Batch evaluation with dry-run mode

### 5. Registry Extension (`core/signals/registry.py`)
- `query_open(min_age_seconds, signal_class, limit)`: finds emitted signals older than threshold
- Filters by lifecycle (only 'emitted'), age, and optional signal_class
- Ordered by created_at ASC for fair evaluation order

### 6. CLI Runner (`core/outcome_tracker.py`)
- `python -m core.outcome_tracker --once [--dry-run]`
- Options: `--db-path`, `--signal-db-path`, `--window-seconds`, `--min-move-pct`, `--limit`, `--log-level`
- Clean summary output with stats dict
- Exit code 1 on errors, 0 on success

### 7. Tests (61 new)
- `test_outcome_model.py`: 18 tests (model validation, safety invariants)
- `test_outcome_evaluator.py`: 16 tests (classification bullish/bearish/neutral, evaluation pipeline, batch, dry-run)
- `test_outcome_repository.py`: 18 tests (insert, upsert, query, export, extra fields)
- `test_outcome_tracker_cli.py`: 9 tests (query_open, CLI runner, dry-run, idempotent rerun)

## Changed Files

| File | Status | Lines |
|------|--------|-------|
| `core/outcomes/__init__.py` | NEW | 1 |
| `core/outcomes/model.py` | NEW | 58 |
| `core/outcomes/repository.py` | NEW | 255 |
| `core/outcomes/evaluator.py` | NEW | 267 |
| `core/outcomes/price_provider.py` | NEW | 54 |
| `core/outcome_tracker.py` | NEW | 159 |
| `core/signals/registry.py` | MODIFIED | +28 |
| `tests/core/test_outcome_model.py` | NEW | 148 |
| `tests/core/test_outcome_evaluator.py` | NEW | 247 |
| `tests/core/test_outcome_repository.py` | NEW | 160 |
| `tests/core/test_outcome_tracker_cli.py` | NEW | 233 |
| `.gitignore` | MODIFIED | +1 |
| **Total** | | **+1611** |

## Validation

```
pytest tests/  → 578 passed, 0 failures, 1 upstream Starlette warning
ruff check .   → 0 errors
Safety         → PASS (can_execute=False, dry_run_only=True)
CLI --once     → exit=0, clean summary
```

## Safety Confirmations

- ✅ No live trading capability
- ✅ No order execution
- ✅ No strategy modulation
- ✅ No weight changes
- ✅ No auto-learning or auto-parameter changes
- ✅ No external heavy dependencies added
- ✅ Idempotent evaluation (safe to rerun)
- ✅ Graceful degradation on missing price data
- ✅ Existing tests preserved (517 → 578)

## Known Limitations

1. **StaticPriceProvider default returns 0.0** — real price feed needed for production use
2. **No background scheduling** — CLI must be run manually or via cron
3. **No heartbeat integration** — future work to add heartbeat when running as daemon
4. **Evaluation window is fixed per run** — cannot vary per signal class yet
5. **No training pipeline** — outcome data is export-ready but no ML training in this PR

## Deferred Items

- Live price provider (exchange API integration) — needs credentials
- Background scheduler for periodic evaluation — future PR
- Training data pipeline (XGBoost, etc.) — separate issue
- Per-signal-class evaluation windows — enhancement
- Heartbeat integration for daemon mode — enhancement

## Architecture Decision: Observational Only

This PR establishes the data layer for self-improvement WITHOUT any feedback into the
signal generation pipeline. The outcome records exist purely as a training-ready dataset.
Future PRs can consume this data for ML training, but that requires separate safety review.

## Dependency on Existing Systems

```
core/signals/envelope.py      → SignalDirection, SignalClass (read-only)
core/signals/registry.py      → query_open() (new method, additive)
storage/canonical_signals.db  → read-only (signal source)
storage/outcomes.db           → new, isolated database
```
