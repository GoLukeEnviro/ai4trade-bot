# AI4TradeBot Signal & Intelligence Layer Roadmap

Date: 2026-06-08
Repo: `GoLukeEnviro/ai4trade-bot`
Status: Planning baseline / implementation roadmap

---

## Executive verdict

The project should not create a separate `trading-hub` system. The correct direction is to evolve the existing `ai4trade-bot` into a unified **Signal & Intelligence Layer** that connects the current Legacy signal producer and the Rainbow Intelligence Engine through a canonical signal contract.

The implementation should remain **signal-only / dry-run-first**. No live execution, no automatic order placement and no LLM-driven trade authority should be introduced by this roadmap.

Recommended first principle:

```text
Signal = structured market/risk/system observation + reason codes + confidence + risk + validity window + data-quality state.
```

---

## Current repository state

### Existing architecture facts

The repo already contains two complementary runtime paths:

1. **Legacy Signal Producer**
   - Entry point: `main.py`
   - Flow: market data -> technical analysis -> market context -> sentiment -> strategy -> signal router -> publisher/store
   - Existing signal model: `core.signal_model.Signal`
   - Existing routing layer: `trading.signal_router.SignalRouter`
   - Existing persistence: `storage.sqlite_repository.SqliteSignalRepository`

2. **Rainbow Intelligence Engine**
   - Entry point: `rainbow/main.py`
   - Flow: collectors -> scorer -> optional LLM evaluation -> SQLite store -> REST API/webhooks
   - Existing signal model: `rainbow.models.signal.CryptoSignal`
   - Existing persistence: `rainbow.processor.store.SignalStore`
   - Existing API: `/health`, `/signals/latest`, `/signals/{signal_id}`, `/metrics`, webhook endpoints
   - Existing collectors: TA, Twitter, Reddit, News

### Important implication

This is not a greenfield build. The first implementation step is **unification**, not reinvention.

The existing models are useful but incomplete for the researched target state:

- Legacy `Signal` is compact and dry-run protected, but lacks canonical type/subtype, risk score, validity window, reason codes and data quality.
- Rainbow `CryptoSignal` already covers source, asset, signal type, direction, strength, confidence, raw data, metadata, score and AI evaluation, but lacks explicit actionability, invalidation and unified risk/data-quality contracts.
- Rainbow already has a signal store and API; Legacy already has a router and SQLite repository.

---

## Target concept

### Target data flow

```text
Legacy Signal Producer                 Rainbow Intelligence Engine
       |                                           |
       v                                           v
LegacySignalAdapter                    RainbowSignalAdapter
       \                                           /
        \                                         /
         v                                       v
            Canonical Signal Envelope
                    |
                    v
          Risk & Quality Gate
                    |
                    v
          Signal Registry / Lifecycle Store
                    |
                    v
     API / Webhook / Telegram / Agent Context
```

### Non-goals

- No separate `trading-hub` repo.
- No live trading implementation.
- No automatic order execution.
- No mandatory Grafana stack.
- No LLM authority to override deterministic risk gates.
- No raw exchange payloads or secrets in public API responses, alerts or docs.

---

## Canonical signal taxonomy

### P0 signal classes

These are required for the first usable version:

| Class | Purpose |
|---|---|
| `ENTRY` | Potential entry candidate, not an execution command |
| `EXIT` | Suggested exit or trade-idea close condition |
| `INVALIDATION` | The original setup is no longer valid |
| `RISK` | Volatility, spread, stale data, drawdown, liquidity or source risk |
| `REGIME` | Market state such as trend, range, high volatility, risk-on/risk-off |
| `SYSTEM_HEALTH` | Runtime, collector, webhook, heartbeat or pipeline health |
| `DATA_QUALITY` | Freshness, missing bars, source latency, degraded feed or malformed data |

### P1 signal classes

These should follow once P0 contracts are stable:

| Class | Purpose |
|---|---|
| `TECHNICAL_CONFLUENCE` | Multi-indicator and multi-timeframe confirmation |
| `VOLATILITY` | ATR spike, volatility compression/expansion, Bollinger width |
| `LIQUIDITY` | Spread, slippage, low-liquidity or volume stress |
| `DERIVATIVES_POSITIONING` | Funding, open interest, long/short, basis, liquidation risk |
| `SIGNAL_LIFECYCLE` | Emitted, expired, invalidated, resolved win/loss |

### P2/P3 signal classes

These are valuable but should not block the MVP:

| Class | Priority | Reason |
|---|---:|---|
| `ORDERFLOW` | P2 | Needs latency-aware data handling |
| `ORDERBOOK_IMBALANCE` | P2 | Useful as context/risk, risky as sole entry trigger |
| `SOCIAL_SENTIMENT` | P2 | Already partially supported by Rainbow collectors, but noisy |
| `NEWS_EVENT` | P2 | Useful risk overlay, needs de-duplication and source quality |
| `ONCHAIN_FLOW` | P2 | High value for crypto, but needs reliable external data adapters |
| `WHALE_ACTIVITY` | P2 | Useful but noisy/manipulable without source rules |
| `LLM_OPINION` | P3 | Must remain explanation/enrichment only, never authority |
| `NARRATIVE_ROTATION` | P3 | Requires historical narrative baselines |
| `SCAM_EXPLOIT_RISK` | P3 | Important later as emergency risk signal |

---

## Canonical signal envelope

The canonical schema should sit between Legacy/Rainbow and the future registry/API/agent layer.

```json
{
  "id": "uuid",
  "schema_version": 1,
  "class": "RISK",
  "subtype": "FUNDING_EXTREME_POSITIVE",
  "source": "rainbow:collector:derivatives",
  "asset": "BTC/USDT",
  "timeframe": "15m",
  "created_at": "2026-06-08T16:00:00Z",
  "valid_until": "2026-06-08T16:15:00Z",
  "direction": "neutral",
  "confidence": 0.78,
  "risk_score": 0.82,
  "priority": "high",
  "reason_codes": [
    "funding_rate_extreme",
    "open_interest_rising",
    "price_extended"
  ],
  "features": {
    "funding_rate": 0.0008,
    "open_interest_change_pct": 4.2,
    "atr_pct": 1.6
  },
  "data_quality": {
    "status": "ok",
    "source_latency_ms": 420,
    "source_quality": "exchange_api",
    "freshness_seconds": 12
  },
  "actionability": {
    "can_alert": true,
    "can_execute": false,
    "dry_run_only": true
  },
  "invalidation": {
    "max_age_seconds": 900,
    "conditions": ["funding_normalized", "oi_reversed"]
  },
  "raw_refs": ["registry://source_snapshot/abc123"]
}
```

### Required rules

- `confidence` and `risk_score` must remain separate.
- Every actionable signal needs `valid_until` or an equivalent invalidation rule.
- Every signal needs reason codes.
- Every signal needs a data-quality state.
- `can_execute` must remain `false` for this roadmap.
- `dry_run_only` must default to `true` and must not be user-overridable by collectors.

---

## Implementation roadmap

### Phase 0 — Planning and safety baseline

Goal: lock the architecture direction before code changes.

Tasks:

- Store this roadmap under `docs/plans/`.
- Add implementation issues for the smallest safe steps.
- Keep prior observability work aligned with this roadmap.
- Explicitly document that this layer does not execute live orders.

Done when:

- Roadmap exists.
- Issues exist.
- No live-order code was introduced.

---

### Phase 1 — Canonical schemas and adapters

Goal: introduce schema contracts without changing runtime behavior.

Tasks:

- Add `core/signals/envelope.py` or equivalent.
- Define `SignalClass`, `SignalDirection`, `SignalPriority`, `DataQualityStatus`, `Actionability`, `InvalidationRule`, `CanonicalSignalEnvelope`.
- Add adapter functions:
  - `from_legacy_signal(core.signal_model.Signal) -> CanonicalSignalEnvelope`
  - `from_rainbow_signal(rainbow.models.signal.CryptoSignal) -> CanonicalSignalEnvelope`
- Keep existing models intact.
- Add unit tests for conversion and dry-run defaults.

Done when:

- Existing Legacy and Rainbow tests still pass.
- New schema tests prove defaults and mappings.
- No persistence migration is required yet.

---

### Phase 2 — Signal registry and lifecycle store

Goal: persist canonical signals without replacing existing stores immediately.

Tasks:

- Add `core/signals/registry.py`.
- Start simple: JSONL or SQLite table for canonical envelopes.
- Store lifecycle events:
  - `emitted`
  - `expired`
  - `invalidated`
  - `resolved_win`
  - `resolved_loss`
- Add query helpers:
  - latest by asset
  - latest by class
  - active signals
  - expired signals
- Keep Legacy `SqliteSignalRepository` and Rainbow `SignalStore` until migration is proven safe.

Done when:

- Canonical signals can be appended and queried.
- No existing store is removed.
- Tests cover write/read/lifecycle transitions.

---

### Phase 3 — Risk and data-quality gate

Goal: avoid noisy or unsafe alerts by scoring risk and input quality before distribution.

Tasks:

- Add `core/signals/risk_gate.py`.
- Compute or normalize:
  - `risk_score`
  - `data_quality.status`
  - `priority`
  - `can_alert`
- Convert existing `MarketSignalAnalyzer.feed_health` into canonical `DATA_QUALITY` / `RISK` signals.
- Suppress alerts for high-risk/low-quality signals unless class is `SYSTEM_HEALTH`, `DATA_QUALITY` or emergency `RISK`.

Done when:

- Stale/degraded feed creates a canonical risk/data-quality signal.
- High-risk entry signals are stored but not alerted as actionable.
- Tests cover alert suppression.

---

### Phase 4 — Runtime integration: Legacy first

Goal: connect the Legacy signal producer to the canonical layer with minimal surface area.

Tasks:

- In `main.py`, convert generated Legacy `Signal` objects into canonical envelopes before or after `SignalRouter.route()`.
- Store canonical envelopes in the registry.
- Add `SYSTEM_HEALTH` / `DATA_QUALITY` envelopes when feed health is degraded.
- Do not change `Strategy.decide()` behavior.
- Do not change publisher behavior except optional canonical side-write.

Done when:

- Legacy still publishes existing signals as before.
- Canonical registry receives converted signals.
- Degraded feed emits a canonical health/risk signal.

---

### Phase 5 — Runtime integration: Rainbow second

Goal: connect Rainbow to the same canonical registry without breaking existing API/store.

Tasks:

- Convert `CryptoSignal` to canonical envelope after scoring/evaluation.
- Store canonical envelope alongside existing `SignalStore.save(sig)`.
- Preserve `/signals/latest` behavior.
- Add optional endpoint later for canonical signals, for example `/signals/canonical/latest`.

Done when:

- Rainbow keeps current API/store behavior.
- Canonical registry receives scored Rainbow signals.
- AI evaluation stays enrichment-only.

---

### Phase 6 — API, Telegram summary and agent context

Goal: expose useful summaries without requiring Grafana.

Tasks:

- Add internal-only API endpoints:
  - `GET /signals/canonical/latest`
  - `GET /risk/latest`
  - `GET /sources/status`
  - `GET /context/agent-summary`
- Add Telegram summary rules:
  - high-priority risk
  - stale collector/feed
  - high-confidence entry with acceptable risk
  - webhook/LLM/system failure
- Add cooldown to prevent alert spam.

Done when:

- Agent summary returns current market/signal/risk state.
- Telegram alerts do not fire for every low-value signal.
- No secrets are exposed.

---

### Phase 7 — P1/P2 adapters after core is stable

Goal: add richer intelligence only after the canonical core works.

Candidate adapters:

- Derivatives positioning: funding, open interest, basis, liquidation risk.
- Liquidity/orderbook: spread, imbalance, wall detection as context/risk only.
- Social/news: Reddit/X/news volume and sentiment with anti-noise gates.
- On-chain: exchange inflow/outflow, whale transfers, stablecoin flows.

Rules:

- New adapters must emit canonical envelopes.
- New adapters must include source quality.
- No adapter may trigger live execution.
- Social/LLM signals must be context/risk overlays unless later validation proves otherwise.

---

## Recommended issue breakdown

1. `Define canonical signal envelope and adapter contracts`
2. `Add canonical signal registry and lifecycle events`
3. `Add risk and data-quality gate for canonical signals`
4. `Connect Legacy signal producer to canonical registry`
5. `Connect Rainbow signals to canonical registry`
6. `Add internal signal/risk/agent-context API endpoints`
7. `Add Telegram summary rules for high-priority intelligence signals`
8. `Plan P1/P2 adapters: derivatives, liquidity, social, on-chain`

---

## Safety policy for implementation

- Default mode remains `dry_run` / signal-only.
- No automatic order execution.
- No live exchange key activation.
- No raw secrets in logs, metrics, alerts, docs or persisted signal payloads.
- LLM output is advisory only.
- Risk gate must be deterministic.
- Data-quality degradation must reduce actionability.
- Unknown/experimental signals can be stored but must not become high-priority alerts by default.

---

## MVP definition

The first usable version is complete when:

- A canonical signal envelope exists.
- Legacy and Rainbow can both map into it.
- Canonical signals can be persisted.
- Each signal has confidence, risk score, data quality, reason codes and validity/invalidation.
- System/data-quality problems can emit first-class signals.
- Alerts are summary-based and cooldown-protected.
- No live execution exists.

---

## Open design decisions

1. Registry backend: JSONL first or SQLite first?
   - Recommendation: SQLite if we want queryability; JSONL if we want minimal first patch.

2. Canonical API location:
   - Recommendation: start under Rainbow FastAPI because it already exposes `/health` and `/signals/latest`.

3. Whether to migrate existing stores:
   - Recommendation: no migration in first pass. Side-write canonical envelopes until stable.

4. Whether to model P0 classes as enums or strings:
   - Recommendation: enums in Python, persisted as stable lowercase strings.

5. Whether Legacy `Signal` should be expanded directly:
   - Recommendation: no direct breaking expansion first. Add adapter layer first, then refactor later.
