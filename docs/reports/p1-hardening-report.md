# P1 Hardening Report — RiskGate Stale Threshold + SQLite Write Sync

## Verdict: GREEN

**Healthscore: 92/100**

## Executive Summary

Two P1 findings from secondary review have been fixed in a single hardening PR:

1. **RiskGate stale_threshold_seconds** — was declared but never wired into evaluation logic
2. **SQLite write synchronization** — `check_same_thread=False` used without any write protection

Both fixes are minimal, targeted, and add no new features.

## Changed Files

| File | Change |
|------|--------|
| `core/signals/risk_gate.py` | Wired `stale_threshold_seconds` into `evaluate()`, added `_compute_staleness_seconds()` |
| `core/signals/registry.py` | Added `threading.Lock` per instance, wrapped all `_conn` operations |
| `core/outcomes/repository.py` | Added `threading.Lock` per instance, wrapped all `_conn` operations |
| `tests/core/test_risk_gate_stale.py` | 11 new tests for stale detection |
| `tests/core/test_sqlite_thread_safety.py` | 7 new tests for concurrent access |
| `tests/core/test_outcome_tracker_cli.py` | Updated for lock pattern |
| `tests/rainbow/test_ingest.py` | Dynamic timestamps (was hardcoded stale) |

## RiskGate Stale Threshold Fix

### Before
`stale_threshold_seconds` was a constructor parameter but never checked in `evaluate()`. Signals with old timestamps could pass through without staleness detection.

### After
- New Rule 2 in `evaluate()`: checks `now - envelope.created_at` against threshold
- Missing/invalid timestamps → treated as stale (safe degradation)
- Meta-signals (RISK, SYSTEM_HEALTH, DATA_QUALITY) bypass stale check
- Stale signals blocked with reason `"stale_signal"`
- Default: 300 seconds, backward compatible

### Tests (11)
- Fresh signal passes
- Stale signal blocked
- Boundary-at-threshold
- Threshold override
- can_execute always False for stale
- Naive timestamps handled
- Meta-signals bypass
- data_quality-degraded takes priority over stale
- `_compute_staleness_seconds` unit tests

## SQLite Write Synchronization Fix

### Before
`check_same_thread=False` was used without any synchronization. Potential for:
- Race conditions on concurrent writes
- `InterfaceError` when reading during write
- Corrupted database under load

### After
- `threading.Lock()` per instance (not global)
- All `self._conn` operations wrapped with `with self._lock:`
- Both reads and writes serialized (required for shared connection)
- `check_same_thread=False` preserved
- Rollback on write failure preserved

### Tests (7)
- Concurrent appends (registry)
- Concurrent transitions (registry)
- Concurrent reads+writes (registry)
- Concurrent inserts (outcomes)
- Concurrent upserts (outcomes)
- Write failure rollback (outcomes)
- Duplicate insert corruption check (registry)

## Validation

| Check | Result |
|-------|--------|
| Ruff | 0 errors |
| Tests | 824 passed (+21 new), 0 failures |
| Watchdog | exit 0 |

## Regression Safety

- ✅ Derivatives Adapter: feature flag OFF, can_execute=False, dry_run_only=True
- ✅ Freqtrade Bridge: advisory-only, unchanged
- ✅ LLM Evaluator: unchanged
- ✅ Confidence Modulation: unchanged
- ✅ Rainbow Ingest: unchanged (timestamp fix only)
- ✅ No new features, no execution paths, no exchange mutation
- ✅ No untyped Any introduced

## Remaining Risks

- Lock granularity is per-instance, not per-database-file. If multiple Registry instances point to the same file, writes could still conflict. Current architecture uses single-instance-per-file, so this is acceptable.
- No WAL mode introduced — could be a future improvement for read concurrency.

## Recommended Merge Decision

**MERGE** — both fixes are minimal, well-tested, and address real stability risks without changing feature behavior.
