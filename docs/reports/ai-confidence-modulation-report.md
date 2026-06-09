# AI Confidence Modulation — Implementation Report (Issue #35)

**Date:** 2026-06-09
**Branch:** `feature/ai-confidence-modulation`
**PR:** https://github.com/GoLukeEnviro/ai4trade-bot/pull/41
**Status:** Open (not merged)

---

## Summary

Implemented a conservative AI confidence modulation layer that safely reduces LLM confidence based on risk signals, uncertainty, warnings, and data completeness. The module is purely advisory — not wired into any execution path.

## Files Created

| File | Lines | Description |
|------|-------|-------------|
| `core/signals/confidence_modulation.py` | 360 | ConfidenceBand enum, ModulatedConfidence model, ConfidenceModulator class |
| `tests/core/test_confidence_modulation.py` | 688 | 76 test cases covering all rules, edge cases, and safety invariants |

## Design

### ConfidenceBand Enum

| Band | Range | Meaning |
|------|-------|---------|
| `HIGH` | ≥ 0.7 | Signal is actionable with moderate-to-high confidence |
| `MEDIUM` | ≥ 0.4 | Signal warrants caution; reduced position sizing |
| `LOW` | ≥ 0.1 | Signal is marginal; prefer HOLD or very small position |
| `BLOCKED` | < 0.1 | Signal suppressed; do not act |
| `UNKNOWN` | N/A | Raw confidence was unavailable; treat as LOW or worse |

### ModulatedConfidence Model

- `raw_confidence`: float | None — original LLM confidence
- `uncertainty`: float | None — derived from 1.0 - confidence
- `risk_level`: str — from AIEvaluation
- `final_confidence`: float [0-1] — conservative normalized result
- `confidence_band`: ConfidenceBand — categorical classification
- `confidence_modulation_reason`: list[str] — human-readable audit trail
- `safety_cap_applied`: bool — whether risk cap reduced confidence
- `risk_modifier`: float [0-1] — ratio of risk-capped to raw confidence

### Modulation Rules (Applied in Order)

1. **Raw confidence extraction** — from `AIEvaluation.ai_confidence` or dict key
2. **Missing/invalid defaults** — None/invalid → 0.3, add reason
3. **Risk caps** — hard ceiling, never exceeded:
   - `extreme` → 0.15
   - `high` → 0.35
   - `medium` → 0.65
   - `low` → no cap (1.0)
4. **Uncertainty penalty** — confidence < 0.5 → reduce by 10%
5. **Warning penalty** — 5% per warning, max 20% reduction
6. **Data completeness penalty** — score < 0.7 → reduce by 15%
7. **Floor at 0.0** — confidence never goes negative
8. **Re-apply risk cap** — penalties can't push above cap
9. **NEVER increase** — final_confidence ≤ raw_confidence always
10. **Map to ConfidenceBand** — per thresholds above

### Error Handling

- `modulate()` never raises — all exceptions produce safe defaults
- Safe defaults: `final_confidence=0.0`, `confidence_band=BLOCKED`, `risk_modifier=0.0`
- All extraction helpers use try/except with conservative fallbacks

## Safety Guarantees

| Guarantee | Status |
|-----------|--------|
| Confidence may ONLY decrease, NEVER increase | ✅ Verified by 76 tests |
| HOLD never becomes BUY/SELL | ✅ Module does not touch signal direction |
| High risk_level caps maximum confidence | ✅ Risk caps are hard ceiling |
| Missing fields → safe conservative defaults | ✅ None/invalid → 0.3 or BLOCKED |
| `modulate()` never raises | ✅ All error paths tested |
| No untyped `Any` | ✅ All types explicit |
| No execution authority | ✅ Purely advisory |
| No exchange credentials accessed | ✅ No network calls |
| Existing bridge unchanged | ✅ Only additive files |
| Existing LLM prompt unchanged | ✅ No modifications |

## Test Results

```
736 passed, 0 failed, 1 warning in 12.56s
Ruff: All checks passed
Watchdog: OK (exit 0, pre-existing heartbeat warnings)
```

### Test Coverage (76 test cases)

| Category | Tests |
|----------|-------|
| High confidence + low risk → HIGH | 3 |
| High confidence + high risk → LOW | 3 |
| High confidence + extreme risk → BLOCKED | 3 |
| Medium confidence + medium risk → MEDIUM | 2 |
| Low confidence + uncertainty penalty | 2 |
| None confidence → UNKNOWN | 2 |
| Invalid negative confidence | 2 |
| Invalid >1.0 confidence | 2 |
| Warning reductions | 4 |
| Max warning cap (20%) | 2 |
| Data completeness penalty | 3 |
| Risk cap never exceeded | 4 |
| modulate() never raises | 6 |
| HOLD bias (final ≤ raw) | 6 |
| Empty AIEvaluation | 1 |
| Malformed dict input | 4 |
| Reason audit trail | 4 |
| Safety cap flag | 4 |
| Risk modifier | 4 |
| Backward compatibility | 2 |
| Uncertainty field | 3 |
| Combined penalties | 2 |
| ConfidenceBand mapping | 5 |
| Dict input path | 3 |
| Model validation | 2 |

## Integration Notes

The confidence modulation module is **not yet wired** into the Freqtrade bridge or any execution path. Future integration would:

1. Call `ConfidenceModulator.modulate(ai_evaluation)` after LLM evaluation
2. Use `ModulatedConfidence.final_confidence` instead of raw `ai_confidence` in downstream decisions
3. Use `ModulatedConfidence.confidence_band` for categorical filtering
4. Log `confidence_modulation_reason` for audit trail
5. Use `safety_cap_applied` and `risk_modifier` for risk reporting

## PR

Opened as **PR #41**: https://github.com/GoLukeEnviro/ai4trade-bot/pull/41
**Not merged** — awaiting review per task requirements.