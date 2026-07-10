# Rainbow Read-Only Signal Provider Contract

> **Status:** Draft — Issue #51
> **System:** GoLukeEnviro/ai4trade-bot → GoLukeEnviro/trading-hub
> **Phase:** SI v2 Phase 0 foundation
> **Last updated:** 2026-06-10

---

## 1. Purpose and Scope

This document defines the **minimum read-only contract** that allows `trading-hub` / Hermes to consume Rainbow signals from `ai4trade-bot` without mutating Rainbow runtime or strategy behavior.

### In scope (Phase 0)

- Inventory of current Rainbow signal surfaces
- Canonical signal envelope definition for cross-system exchange
- Null, error, stale, and heartbeat behavior rules
- Schema versioning and redaction policy
- Read-only boundary documentation

### Explicitly out of scope (Phase 0)

- Live runtime integration or deployment
- Strategy or model changes in Rainbow
- Real-time subscription infrastructure (WebSocket, streaming)
- Historical backfill or batch export pipelines
- Signal replay or event sourcing
- Trading execution or order routing
- Credential or secret management
- Any mutation of ai4trade-bot runtime behavior

---

## 2. Read-Only Boundary

The following constraints are **non-negotiable** and apply to every component that touches Rainbow signals in a trading-hub context:

| Constraint | Effect |
|-----------|--------|
| No live trading | All signals are consumed in `dry_run=true` context |
| No strategy mutation | Rainbow strategy code, parameters, and model weights are read-only |
| No credential reads | API keys, tokens, secrets are never read, printed, or forwarded |
| No runtime mutation | No container restart, config change, or service reload |
| No cron/scheduler change | No activation or modification of recurring jobs |
| No exchange access | No read or write to exchange endpoints |
| No downstream execution | Signals inform analysis only — they never trigger orders |

The `CanonicalSignalEnvelope` (see §4) enforces these programmatically via `Actionability._enforce_safety()` which sets `can_execute=False` and `dry_run_only=True` on every envelope.

---

## 3. Current Rainbow Signal Inventory

### 3.1 Signal Models

Rainbow defines two signal representations:

| Model | Location | Purpose |
|-------|----------|---------|
| `CryptoSignal` | `rainbow/models/signal.py` | Internal Rainbow signal — used within the Rainbow subsystem |
| `CanonicalSignalEnvelope` | `core/signals/envelope.py` | Universal cross-system signal container — used for external distribution |

### 3.2 API Surface

Rainbow exposes signals via FastAPI:

| Endpoint | Method | Returns | Description |
|----------|--------|---------|-------------|
| `/signals/latest` | GET | `list[dict]` | Latest signals, filterable by asset/source/signal_type |
| `/signals/{signal_id}` | GET | `dict` | Single signal by ID |
| `/signals/canonical/latest` | GET | `list[dict]` | Latest canonical envelopes, filterable by asset/class |
| `/risk/latest` | GET | `list[dict]` | Latest risk signals |
| `/health` | GET | `dict` | Health status + collector status |
| `/metrics` | GET | `dict` | Signal store metrics |
| `/webhooks/subscribe` | POST | subscription ID | Webhook registration (not part of this contract) |

### 3.3 Ingest Pipeline

External signals enter Rainbow via the ingest endpoint mapped by `rainbow/ingest/ingest.py`. The pipeline:

1. Validates `RainbowIngestRequest` (required: asset, direction, strength, source, timestamp)
2. Rate-limits per source (60 req/min default)
3. Creates `CanonicalSignalEnvelope` with `Actionability(can_execute=False, dry_run_only=True)`
4. Stores in `CanonicalSignalRegistry`
5. Passes through `RiskGate` (rejects if stale/blacklisted)
6. Returns `RainbowIngestResult` with status and signal_id

### 3.4 Existing Signal Consumers

| Consumer | Mechanism | Read-Only? |
|----------|-----------|------------|
| `rainbow/distribution/webhooks.py` | HTTP POST to subscribed URLs | Yes (push-only) |
| `integrations/freqtrade_bridge.py` | Freqtrade strategy import | Yes (reads signal state) |
| `integrations/primoagent_bridge.py` | PrimoAgent format export | Yes |
| `/signals/*` API endpoints | REST GET | Yes |

---

## 4. Canonical Signal Envelope

The `CanonicalSignalEnvelope` (`core/signals/envelope.py`) is the **universal signal container** and the preferred format for trading-hub consumption.

### 4.1 Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `str` (UUID4) | ✅ | Unique signal identifier |
| `schema_version` | `int` | ✅ | Envelope schema version (currently `1`) |
| `class` (alias: `signal_class`) | `SignalClass` enum | ✅ | `entry`, `exit`, `invalidation`, `risk`, `regime`, `system_health`, `data_quality` |
| `subtype` | `str` | ✅ | Signal subtype (e.g. `"ta_convergence"`, `"sentiment_shift"`) |
| `source` | `str` | ✅ | Origin identifier (e.g. `"rainbow:ta"`, `"rainbow:llm"`) |
| `asset` | `str` | ✅ | Trading pair (e.g. `"BTC/USDT:USDT"`) |
| `timeframe` | `str \| None` | ❌ | Candle timeframe if applicable (e.g. `"1h"`, `"15m"`) |
| `created_at` | `datetime` (ISO-8601) | ✅ | Timestamp when the envelope was created |
| `valid_until` | `datetime \| None` | ❌ | Expiry timestamp; `None` = use `invalidation` rules |
| `direction` | `SignalDirection` enum | ✅ | `bullish`, `bearish`, or `neutral` |
| `confidence` | `float` [0.0, 1.0] | ✅ | Signal confidence |
| `risk_score` | `float` [0.0, 1.0] | ✅ | Risk assessment (higher = riskier) |
| `priority` | `SignalPriority` enum | ✅ | `critical`, `high`, `medium`, `low` |
| `reason_codes` | `list[str]` | ✅ | Machine-readable reasons (e.g. `["ta_rsi_oversold"]`) |
| `features` | `dict[str, Any]` | ❌ | Arbitrary feature map for model/analysis metadata |
| `data_quality` | `DataQuality` object | ✅ | Status (`ok`, `degraded`, `stale`, `unavailable`), latency, freshness |
| `actionability` | `Actionability` object | ✅ | Always `can_execute=False, dry_run_only=True` (enforced) |
| `invalidation` | `InvalidationRule` object | ✅ | `max_age_seconds` (default 3600) + optional conditions |
| `raw_refs` | `list[str]` | ❌ | References to raw input data that produced this signal |

### 4.2 `CryptoSignal` Model (Rainbow-internal)

The `CryptoSignal` model (`rainbow/models/signal.py`) is used within the Rainbow subsystem and may be converted to `CanonicalSignalEnvelope` for external consumption.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `signal_id` | `str` (UUID4) | ✅ | Unique signal identifier |
| `timestamp` | `datetime` | ✅ | When the signal was generated |
| `source` | `str` | ✅ | Origin (e.g. `"rainbow:ta"`, `"rainbow:llm"`) |
| `asset` | `str` | ✅ | Trading pair |
| `signal_type` | `SignalType` enum | ✅ | `technical`, `sentiment`, `news`, `onchain`, `prediction_market`, `macro`, `social` |
| `direction` | `Direction \| None` | ❌ | `bullish`, `bearish`, `neutral`, or `None` |
| `strength` | `float` [0.0, 1.0] | ✅ | Signal strength |
| `confidence` | `float` [0.0, 1.0] | ✅ | Signal confidence |
| `value` | `float \| None` | ❌ | Numeric value if applicable |
| `raw_data` | `dict \| None` | ❌ | Raw input data (may require redaction) |
| `metadata` | `dict` | ✅ | Arbitrary metadata; known assets include `canonical_symbol` in Trading-Hub format |
| `rainbow_score` | `float \| None` | ❌ | Composite Rainbow score |
| `ai_evaluation` | `AIEvaluation \| None` | ❌ | LLM evaluation result |
| `timeframe` | `str \| None` | ❌ | Candle timeframe |
| `stop_loss`, `take_profit`, `leverage` | `float \| None` | ❌ | Trade parameters if present |

### 4.3 Ingest Request Model

The `RainbowIngestRequest` (`rainbow/ingest/models.py`) defines what external systems must provide:

| Field | Required | Validation |
|-------|----------|------------|
| `asset` | ✅ | Non-empty string, e.g. `"BTC/USDT"` |
| `direction` | ✅ | One of: `bullish`, `bearish`, `neutral` |
| `strength` | ✅ | Float [0.0, 1.0] |
| `source` | ✅ | Non-empty origin identifier |
| `timestamp` | ✅ | ISO-8601 UTC string |
| `rainbow_score` | ❌ | Float [0.0, 1.0] |
| `raw_data` | ❌ | Arbitrary dict |
| `signal_class` | ❌ | String |
| `confidence` | ❌ | Float [0.0, 1.0] |

---

## 5. Required Signal Envelope (for trading-hub consumption)

For trading-hub consumption via the read-only adapter layer (trading-hub #21, merged), the following fields are **required** in every envelope:

```python
{
    "schema_version": 1,
    "source_system": "rainbow",
    "source_id": "rainbow:ta",
    "strategy_id": "rainbow_v1",
    "model_id": None,
    "symbol": "BTC/USDT:USDT",
    "timeframe": "1h",
    "timestamp_utc": "2026-06-10T12:00:00Z",
    "emitted_at_utc": "2026-06-10T12:00:05Z",
    "direction": "short",
    "confidence": 0.85,
    "signal_strength": 0.72,
    "regime_hint": "bearish",
    "metadata": {
        "reason_codes": ["ta_rsi_oversold", "sentiment_bearish"],
        "features": {},
        "raw_refs": []
    },
    "redaction_status": "clean"
}
```

### Field Mapping: Rainbow → trading-hub

| trading-hub Field | Rainbow Source | Transformation |
|-------------------|---------------|----------------|
| `schema_version` | `CanonicalSignalEnvelope.schema_version` | Direct |
| `source_system` | Fixed: `"rainbow"` | Constant |
| `source_id` | `CanonicalSignalEnvelope.source` or `CryptoSignal.source` | Direct |
| `strategy_id` | `CryptoSignal.metadata.get("strategy", "rainbow_v1")` | Optional |
| `model_id` | `CryptoSignal.metadata.get("model_id")` | Optional |
| `symbol` | `CanonicalSignalEnvelope.asset` or `CryptoSignal.metadata["canonical_symbol"]` | Direct; must use canonical `BASE/QUOTE:QUOTE` format |
| `timeframe` | `CanonicalSignalEnvelope.timeframe` or `CryptoSignal.timeframe` | Direct |
| `timestamp_utc` | `CanonicalSignalEnvelope.created_at` or `CryptoSignal.timestamp` | ISO-8601 |
| `emitted_at_utc` | System timestamp at envelope creation | Optional |
| `direction` | Mapped from `SignalDirection` or `Direction` | See §5.1 |
| `confidence` | `CanonicalSignalEnvelope.confidence` or `CryptoSignal.confidence` | 0.0–1.0 |
| `signal_strength` | `CryptoSignal.strength` | Optional |
| `regime_hint` | `CryptoSignal.metadata.get("regime")` | Optional |
| `metadata` | Combination of `features`, `reason_codes`, `raw_refs`, `data_quality` | Merged |

For known Rainbow assets, `CryptoSignal.asset` remains the collector-friendly base asset (`BTC`, `ETH`, `SOL`) and
`metadata.canonical_symbol` carries the cross-system symbol (`BTC/USDT:USDT`, `ETH/USDT:USDT`,
`SOL/USDT:USDT`). Consumers must reject an unmapped asset rather than infer a trading pair.

### 5.1 Direction Mapping

| Rainbow Direction | trading-hub Direction |
|-------------------|----------------------|
| `bullish` | `long` |
| `bearish` | `short` |
| `neutral` | `flat` |
| Signal generator explicitly reports no signal | `no_signal` |
| Direction cannot be determined | `unknown` |

---

## 6. Null / No-Signal Behavior

| Condition | Behavior |
|-----------|----------|
| No signal generated for a watched asset | No envelope produced — absence is not an error |
| Empty signal list from API | Return `[]` — caller must handle empty results gracefully |
| Signal direction is `None` | Treat as `unknown` — do not infer or default |
| `confidence` or `strength` missing | Reject envelope — these are required |
| `asset` missing or empty | Reject envelope immediately |

---

## 7. Error Behavior

| Condition | Response | Envelope Produced? |
|-----------|----------|-------------------|
| Malformed ingest request (invalid field types) | `HTTP 422` — validation error details | No |
| Ingest rate limit exceeded (60 req/min/source) | `HTTP 429` — rate limit message | No |
| Ingest request missing required field | `HTTP 422` — field-level error | No |
| Signal store unavailable (503) | `HTTP 503` — "Signal store not ready" | No |
| Signal ID not found | `HTTP 404` — "Signal '...' not found" | N/A |
| Invalid direction string | `ValueError` — must be one of: bullish, bearish, neutral | No |
| Invalid asset (empty after strip) | `ValueError` — must be non-empty | No |

All ingest failures **fail closed** — no partial signal is stored or forwarded.

---

## 8. Heartbeat Behavior

The Rainbow system provides health signals via the `/health` endpoint:

```json
{
    "status": "healthy",
    "collectors": {
        "ta": "running",
        "news": "running",
        "reddit": "stopped",
        "twitter": "running"
    },
    "uptime_seconds": 123456.7
}
```

- **No trading decisions** should be based on heartbeat data.
- Heartbeat confirms producer availability only.
- If `/health` returns non-`healthy` or is unreachable for 3 consecutive checks, mark the signal source as `UNAVAILABLE`.

---

## 9. Stale Signal Behavior

| Condition | Detection | Action |
|-----------|-----------|--------|
| Signal exceeds `InvalidationRule.max_age_seconds` (default 3600) | `CanonicalSignalEnvelope` invalidation rules | Mark signal as stale; do NOT use for current decisions |
| `/health` unreachable for ≥3 checks | External monitoring | Mark all signals from this source as `UNAVAILABLE` |
| `data_quality.status == DataQualityStatus.STALE` | Envelope field | Consumer must reject envelope immediately |
| `data_quality.status == DataQualityStatus.UNAVAILABLE` | Envelope field | Consumer must back off and not request until health recovers |

Stale signals must **never** be used as evidence for current trading decisions.

---

## 10. Schema Versioning

| Version | Date | Changes |
|---------|------|---------|
| 1 | 2026-06-10 | Initial contract definition |

The `schema_version` field in the envelope allows forward compatibility. Consumers must:
- Accept envelopes with `schema_version >= 1`
- Reject envelopes with `schema_version < 1`
- Log a warning for `schema_version > known` for observability

---

## 11. Redaction and Secret Policy

No credentials, API keys, tokens, or secrets are part of the signal envelope. The following rules apply:

| Field | Redaction Required? | Reason |
|-------|--------------------|--------|
| `features` | Maybe | If downstream features contain raw data, may require review |
| `raw_refs` | Maybe | References to raw data that may contain paths or IDs |
| `metadata` | Check | Arbitrary; consumer must verify before persistence |
| `raw_data` (CryptoSignal) | ✅ | Contains raw collector output — redact before external forwarding |

The `RealFreqtradeAdapter.read_config()` in trading-hub already implements secret key redaction (`api_key`, `secret`, `password`, `token`). A similar pattern should be applied for Rainbow signal metadata.

---

## 12. Out-of-Scope for Phase 0

The following are explicitly deferred and tracked as separate issues:

| Issue | Description | Phase |
|-------|-------------|-------|
| ai4trade-bot #56 | Sanitized signal fixture pack for contract validation | Phase 0 follow-up |
| ai4trade-bot #57 | Read-only signal evidence export method | Phase 0 follow-up |
| ai4trade-bot #58 | Metadata completeness checker for attribution readiness | Phase 0 follow-up |
| trading-hub #79 | Rainbow signal envelope validator with fixture tests | Phase 0 follow-up |
| trading-hub #80 | Read-only Rainbow Signal Provider client behind env gate | Phase 1 |
| trading-hub #81 | Shadowlock audit events for external signal evidence | Phase 1 |

---

## 13. Follow-Up Issues Mapping

```
#51 This Contract
 ├── #56 Fixtures
 ├── #57 Evidence Export
 └── #58 Metadata Checker
      ├── trading-hub #79 Validator
      ├── trading-hub #80 Read-only Client
      └── trading-hub #81 Shadowlock Events
           └── Phase 1 Integration
```

---

## Appendix A: Example Envelopes

### A.1 Valid Long Signal

```python
CanonicalSignalEnvelope(
    schema_version=1,
    signal_class=SignalClass.ENTRY,
    subtype="ta_convergence",
    source="rainbow:ta",
    asset="BTC/USDT:USDT",
    timeframe="1h",
    created_at=datetime(2026, 6, 10, 12, 0, 0),
    direction=SignalDirection.BULLISH,
    confidence=0.85,
    risk_score=0.25,
    priority=SignalPriority.HIGH,
    reason_codes=["ta_rsi_oversold", "trend_reversal"],
    features={"rsi_14": 28.5, "macd_histogram": 12.3},
    data_quality=DataQuality(status=DataQualityStatus.OK, freshness_seconds=30),
    actionability=Actionability(can_alert=True),
    invalidation=InvalidationRule(max_age_seconds=3600),
)
```

### A.2 Valid Short Signal

```python
CanonicalSignalEnvelope(
    schema_version=1,
    signal_class=SignalClass.ENTRY,
    subtype="sentiment_shift_bearish",
    source="rainbow:llm",
    asset="ETH/USDT:USDT",
    timeframe=None,
    created_at=datetime(2026, 6, 10, 12, 30, 0),
    direction=SignalDirection.BEARISH,
    confidence=0.72,
    risk_score=0.60,
    priority=SignalPriority.MEDIUM,
    reason_codes=["sentiment_bearish", "fear_greed_extreme"],
    features={"sentiment_score": 0.22, "fear_greed_index": 15},
    data_quality=DataQuality(status=DataQualityStatus.OK, freshness_seconds=120),
    actionability=Actionability(can_alert=True),
    invalidation=InvalidationRule(max_age_seconds=1800),
)
```

### A.3 No-Signal Event

```python
CanonicalSignalEnvelope(
    schema_version=1,
    signal_class=SignalClass.SYSTEM_HEALTH,
    subtype="no_signal",
    source="rainbow:ta",
    asset="SOL/USDT:USDT",
    created_at=datetime(2026, 6, 10, 13, 0, 0),
    direction=SignalDirection.NEUTRAL,
    confidence=0.0,
    risk_score=0.0,
    priority=SignalPriority.LOW,
    reason_codes=["no_signal_conditions"],
    data_quality=DataQuality(status=DataQualityStatus.OK),
    actionability=Actionability(can_alert=False),
)
```

### A.4 Heartbeat Event

```python
{
    "schema_version": 1,
    "source_system": "rainbow",
    "source_id": "system:health",
    "strategy_id": "rainbow_v1",
    "symbol": "*",
    "timestamp_utc": "2026-06-10T13:00:00Z",
    "direction": "no_signal",
    "confidence": 0.0,
    "metadata": {
        "status": "healthy",
        "collectors": {"ta": "running", "news": "running", "twitter": "running", "reddit": "stopped"},
        "uptime_seconds": 3600
    },
    "redaction_status": "clean"
}
```

### A.5 Stale Signal — Consumer Rejection

```python
# Consumer MUST NOT use this envelope for decisions
if envelope.data_quality.status in (DataQualityStatus.STALE, DataQualityStatus.UNAVAILABLE):
    logger.warning(f"Rejecting stale signal {envelope.id}")
    return  # skip
```

### A.6 Malformed Signal — Rejection Example

```python
# Missing required 'asset' field
try:
    request = RainbowIngestRequest(
        asset="",
        direction="bullish",
        strength=0.8,
        source="test",
        timestamp="2026-06-10T12:00:00Z",
    )
except ValueError as e:
    # Result: HTTP 422 with details
    pass
```

---

## Appendix B: Field Type Reference

| Python Type | JSON Type | Range / Values |
|------------|-----------|----------------|
| `str` | `string` | Arbitrary |
| `int` | `number` | 32-bit integer |
| `float` | `number` | IEEE 754 double |
| `bool` | `boolean` | `true` / `false` |
| `datetime` | `string` | ISO-8601 UTC (`"2026-06-10T12:00:00Z"`) |
| `SignalDirection` | `string` | `"bullish"`, `"bearish"`, `"neutral"` |
| `SignalClass` | `string` | `"entry"`, `"exit"`, `"invalidation"`, `"risk"`, `"regime"`, `"system_health"`, `"data_quality"` |
| `SignalPriority` | `string` | `"critical"`, `"high"`, `"medium"`, `"low"` |
| `DataQualityStatus` | `string` | `"ok"`, `"degraded"`, `"stale"`, `"unavailable"` |
| `Confidence` | `number` | `0.0` — `1.0` |
| `RiskScore` | `number` | `0.0` — `1.0` |
| `Direction (trading-hub)` | `string` | `"long"`, `"short"`, `"flat"`, `"no_signal"`, `"unknown"` |
