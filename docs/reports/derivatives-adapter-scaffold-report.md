# Derivatives Adapter Scaffold Report

**Issue**: #20 — Derivatives Adapter as a DRY-RUN-ONLY scaffold
**Branch**: `feature/derivatives-adapter-dry-run`
**PR**: #43
**Date**: 2026-06-09
**Status**: ✅ Complete — PR open, not merged

---

## Overview

Implemented a dry-run-only derivatives data adapter scaffold for the ai4trade-bot
Python signal intelligence layer. The adapter provides typed protocols for fetching
funding rate and open interest data from derivatives markets, with a stub
implementation that returns static data — no real HTTP calls, no exchange SDK imports,
no live trading.

## Package Structure

```
adapters/derivatives/
├── __init__.py          # Public API exports (5 symbols)
├── models.py            # FundingRate, OpenInterest, DerivativesSignal
├── client.py            # DerivativesDataFetcher ABC + DryRunDerivativesFetcher
└── adapter.py           # DerivativesAdapter wrapper

tests/adapters/
├── __init__.py
└── test_derivatives.py  # 39 tests
```

## Design Decisions

### 1. ABC Protocol (not typing.Protocol)
Used `abc.ABC` for `DerivativesDataFetcher` to enforce implementation at
class-definition time rather than at usage time, consistent with the project's
pattern in `core/signals/risk_gate.py` and `integrations/freqtrade_bridge.py`.

### 2. Feature Flag Pattern
`DryRunDerivativesFetcher.ENABLED` is a class attribute defaulting to `False`.
This follows the project's conservative safety-first pattern — new features
are disabled by default and must be explicitly enabled.

### 3. Literal Types for Safety Invariants
`DerivativesSignal.can_execute` is typed as `Literal[False]` and
`dry_run_only` as `Literal[True]`. This enforces safety at the type system
level — attempting to set `can_execute=True` or `dry_run_only=False` raises
a Pydantic validation error.

### 4. Never-Raise Pattern
All public methods wrap their logic in try/except and return `None` on any
error. This matches the pattern in `FreqtradeBridge.get_latest_signal()` and
`ConfidenceModulator.modulate()`.

### 5. Async Protocol
Methods are `async def` to prepare for future real implementations that may
use async HTTP clients. The dry-run implementation uses no actual I/O.

## Safety Guarantees

| Guarantee | Mechanism | Verified |
|-----------|-----------|----------|
| No real HTTP calls | No HTTP imports; mocked urllib/requests in tests | ✅ |
| No exchange SDK imports | No ccxt/aiohttp/httpx imports | ✅ |
| No live trading | No order/execution functions exist | ✅ |
| No leverage mutation | No leverage fields exist | ✅ |
| Feature flag disabled by default | `ENABLED: bool = False` class attr | ✅ |
| Methods never raise | try/except returning None | ✅ |
| can_execute always False | `Literal[False]` type | ✅ |
| dry_run_only always True | `Literal[True]` type | ✅ |
| Logs all operations | logging at INFO (enabled) / DEBUG (disabled) | ✅ |

## Test Coverage

39 tests across 12 test classes:

| Test Class | Count | What It Verifies |
|------------|-------|------------------|
| TestFundingRateModel | 7 | Model validation, defaults, required fields, negative rates |
| TestOpenInterestModel | 4 | Model validation, defaults, required fields |
| TestDerivativesSignalModel | 8 | Combined signal, partial data, safety invariants, type enforcement |
| TestDryRunFetcherFeatureFlag | 2 | Default False, can be enabled |
| TestDryRunFetcherDisabled | 2 | Returns None when disabled |
| TestDryRunFetcherEnabled | 2 | Returns stub data when enabled |
| TestDryRunFetcherNeverRaises | 2 | Never raises even with empty input |
| TestDryRunFetcherLogsStubUsage | 2 | Logs "STUB" and "DRY-RUN ONLY" when enabled, "ENABLED=False" when disabled |
| TestDerivativesAdapterDisabled | 1 | Returns None when fetcher disabled |
| TestDerivativesAdapterEnabled | 3 | Returns signal with funding rate + open interest |
| TestDerivativesAdapterNeverRaises | 1 | Never raises |
| TestDerivativesAdapterLogging | 2 | Logs stub usage and disabled state |
| TestNoNetworkCalls | 3 | No urllib/requests calls made |

## Validation Results

| Check | Result |
|-------|--------|
| Ruff check | 0 errors |
| pytest (full suite) | 803 passed, 0 failed |
| watchdog_runner | Clean exit (expected heartbeat warnings) |

## Files Created

1. `adapters/derivatives/__init__.py` — Package init with public exports
2. `adapters/derivatives/models.py` — Data models (FundingRate, OpenInterest, DerivativesSignal)
3. `adapters/derivatives/client.py` — Protocol ABC + DryRunDerivativesFetcher
4. `adapters/derivatives/adapter.py` — DerivativesAdapter wrapper
5. `tests/adapters/__init__.py` — Test package init
6. `tests/adapters/test_derivatives.py` — 39 tests

## Known Limitations (By Design)

- Stub data is hardcoded (`funding_rate=0.01`, `open_interest=1,000,000`)
- No real exchange data — this is a scaffold only
- Async methods use no actual I/O — purely synchronous stub logic
- Feature flag is a class attribute, not a runtime config (future work)
- No integration with CanonicalSignalEnvelope or RiskGate yet (future work)

## Future Integration Points

When this scaffold is promoted to a real implementation:

1. Create a `LiveDerivativesFetcher` subclass with real HTTP client
2. Wire `DerivativesSignal` into `CanonicalSignalEnvelope` as a feature dict
3. Add derivatives-specific rules to `RiskGate`
4. Feed funding rate data into `ConfidenceModulator` as a data quality signal
5. Replace class-attribute feature flag with runtime config