# Rainbow Attribution Metadata Readiness

> **Status:** Phase 0 complete — spec only, no runtime changes  
> **Issue:** #53  
> **Consumer:** GoLukeEnviro/trading-hub (SI v2 Phase 1 prep)

---

## 1. Existing Metadata Fields

### CryptoSignal (`rainbow/models/signal.py`)

| Field | Attribution use |
|-------|-----------------|
| `signal_id` | Unique event id |
| `timestamp` | `generated_at` equivalent |
| `source` | Collector id (`rainbow:ta`, etc.) |
| `asset` | Pair / symbol |
| `signal_type` | Source category |
| `confidence` | Model confidence |
| `timeframe` | Optional candle period |
| `metadata` | Extensible bag |
| `ai_evaluation` | LLM evaluation context |

### CanonicalSignalEnvelope (`core/signals/envelope.py`)

| Field | Attribution use |
|-------|-----------------|
| `id` | Envelope id |
| `schema_version` | Versioning |
| `source` | Provider id |
| `asset` | Trading pair |
| `timeframe` | Period |
| `created_at` | Generation time |
| `valid_until` | Staleness bound |
| `confidence` | Score |
| `features` | Attribution features |
| `reason_codes` | Explainability |
| `data_quality` | Freshness / degradation |

### Export schema (fixtures / trading-hub contract)

| Field | Status |
|-------|--------|
| `source_id` | Required in fixtures |
| `strategy_id` | Required |
| `model_id` | Optional |
| `symbol` | Required |
| `timeframe` | Optional |
| `timestamp_utc` | Required (`generated_at`) |
| `emitted_at_utc` | Optional |
| `confidence` | Required |
| `regime_hint` | Optional — Phase 1 hook |
| `metadata.reason_codes` | Present in fixtures |
| `metadata.data_quality` | Present |
| `redaction_status` | Required |

---

## 2. Missing Fields for Phase 1 Attribution

| Field | Status | Phase 1 action |
|-------|--------|----------------|
| `regime_label` | Not implemented | trading-hub attaches externally |
| `attribution_bucket` | Not implemented | Phase 1 SI scoring |
| `strategy_version` | Partial (`strategy_id` only) | Extend metadata bag |
| `emitted_at` | Optional in export | Populate at publish time |
| `signal_version` | Via `schema_version` | Document mapping |

No blocking gaps — extension via `metadata` dict and `regime_hint` preserves backwards compatibility.

---

## 3. Backwards-Compatible Extension Plan

1. **Phase 0 (now):** Consume existing `metadata` + optional `regime_hint` without requiring new Rainbow code paths.
2. **Phase 1:** trading-hub adds `regime_label` post-ingest; Rainbow may populate `regime_hint` when regime detector exists.
3. **Schema bump:** Increment `schema_version` only when required fields change; old consumers read v1 envelopes via compatibility layer in contract.

### Rules

- New fields are **optional** with null defaults.
- No removal or rename of existing fields without version bump.
- `metadata` dict accepts arbitrary Phase 1 keys without Rainbow redeploy.

---

## 4. Phase 1 Handoff Requirements

trading-hub needs from Rainbow:

- [x] Stable read-only envelope (`CanonicalSignalEnvelope`)
- [x] Documented export schema (fixtures + contract #51)
- [x] `confidence`, `source_id`, `strategy_id`, `symbol`, timestamps
- [ ] Runtime regime detector (Phase 1 — not Rainbow Phase 0)
- [ ] Attribution scoring engine (trading-hub owned)

---

## 5. Verdict

**READY** for Phase 1 attribution integration planning. Metadata surface is sufficient; missing regime/attribution fields are intentionally deferred to trading-hub Phase 1.