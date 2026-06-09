# Freqtrade Integration Guide

> **⚠️ WARNING: Live execution is NOT enabled by this module.**
> The bridge and strategy are advisory-only. They produce HOLD recommendations
> by default and never submit orders. See Safety Invariants below.

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│                    ai4trade-bot Core                       │
│  ┌────────────────┐  ┌────────────────┐  ┌─────────────┐  │
│  │ Signal Sources  │  │ Risk Gate       │  │ Watchdog     │  │
│  │ (Legacy/TA/    │  │ (5-rule filter) │  │              │  │
│  │  Rainbow/AI)   │  │                 │  │              │  │
│  └───────┬────────┘  └───────┬────────┘  └─────────────┘  │
│          │                   │                             │
│          ▼                   │                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  CanonicalSignalRegistry (SQLite, read-only bridge) │  │
│  └──────────────────────┬──────────────────────────────┘  │
└─────────────────────────┼─────────────────────────────────┘
                          │ query_latest() / query_active()
                          ▼
┌───────────────────────────────────────────────────────────┐
│              FreqtradeBridge (integrations/)               │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Policy Checks:                                       │  │
│  │  • can_execute MUST be False                         │  │
│  │  • dry_run_only MUST be True                         │  │
│  │  • Confidence ≥ 0.6                                  │  │
│  │  • Risk score < 0.7                                  │  │
│  │  • Data quality = OK                                 │  │
│  │  • Signal not expired                                │  │
│  │  • Rate limiting per pair                            │  │
│  │  • Cache TTL per pair                                │  │
│  └──────────────────────┬──────────────────────────────┘  │
│                          │ advisory dict: buy/sell/hold      │
│                          ▼                                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  AI4TradeSignalStrategy (IStrategy skeleton)         │  │
│  │  • populate_entry_trend → "buy" advisory → enter 1  │  │
│  │  • populate_exit_trend  → "sell" advisory → exit 1  │  │
│  │  • Default: HOLD (no entries, no exits)              │  │
│  └──────────────────────┬──────────────────────────────┘  │
└─────────────────────────┼─────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────┐
│                    Freqtrade Engine                        │
│  (dry-run mode only — never live trading)                  │
└───────────────────────────────────────────────────────────┘
```

## Data Flow

```
1. Signal producers → CanonicalSignalEnvelope → Registry (SQLite)
2. FreqtradeBridge.get_latest_signal(pair) → Registry query
3. Bridge applies policy checks (confidence, risk, expiry, quality)
4. Bridge returns advisory dict: {"action": "buy"|"sell"|"hold", ...}
5. AI4TradeSignalStrategy maps advisory to populate_entry_trend / populate_exit_trend
6. Freqtrade runs in dry-run mode — no real orders
```

## Configuration

### FreqtradeBridge Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `confidence_threshold` | 0.6 | Minimum confidence for signal to be actionable |
| `risk_threshold` | 0.7 | Maximum risk_score allowed (≥ threshold → HOLD) |
| `cache_ttl_seconds` | 60.0 | Seconds to cache advisory result per pair |
| `min_interval_seconds` | 30.0 | Minimum seconds between calls per pair |

### AI4TradeSignalStrategy Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `stoploss` | -0.05 | 5% stop loss |
| `minimal_roi` | {"0": 0.10, "30": 0.05, "60": 0.02} | Conservative ROI targets |
| `timeframe` | 5m | Candlestick timeframe |
| `confidence_threshold` | 0.6 | Passed to bridge |
| `risk_threshold` | 0.7 | Passed to bridge |

### Example Freqtrade Config Snippet

```json
{
  "trading_mode": "dry_run",
  "dry_run": true,
  "stoploss": -0.05,
  "minimal_roi": {
    "0": 0.10,
    "30": 0.05,
    "60": 0.02
  },
  "strategy": "AI4TradeSignalStrategy",
  "strategy_path": "/path/to/ai4trade-bot/integrations",
  "exchange": {
    "name": "binance",
    "pair_whitelist": [
      "BTC/USDT",
      "ETH/USDT"
    ]
  },
  "signal_registry_path": "storage/canonical_signals.db"
}
```

**CRITICAL:** `"dry_run": true` MUST always be set. Never run this in live mode.

## Safety Invariants

1. **`can_execute` is always `False`** — enforced by Pydantic model_validator on
   `Actionability`. The bridge additionally rejects any signal where `can_execute`
   is not `False`.

2. **`dry_run_only` is always `True`** — enforced by Pydantic model_validator on
   `Actionability`. The bridge rejects any signal where `dry_run_only` is not `True`.

3. **HOLD is always the fallback** — any error, missing signal, expired signal,
   or policy violation returns `{"action": "hold", ...}`.

4. **No live trading** — no order execution, no exchange credentials, no HTTP calls.

5. **No secrets** — no API keys, tokens, or credentials in logs, DB, config, or tests.

6. **All errors caught** — the bridge never raises exceptions; all failures return
   a HOLD advisory with a detailed reason string.

7. **Rate-limited** — minimum interval between calls for the same pair prevents
   signal flooding.

8. **Cached** — results are cached per pair with configurable TTL.

## Policy Check Order

The bridge evaluates signals in this order. The first failing check short-circuits
to HOLD:

1. **Safety invariant** — `can_execute` must be `False`
2. **Safety invariant** — `dry_run_only` must be `True`
3. **Expiry** — `valid_until` must be in the future
4. **Data quality** — status must be `ok`
5. **Confidence** — must be ≥ `confidence_threshold` (default 0.6)
6. **Risk** — `risk_score` must be < `risk_threshold` (default 0.7)
7. **Direction** — mapped to `buy`, `sell`, or `hold`

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Always returns `hold` | No signals in registry | Run signal producer first: `python main.py` |
| `hold: rate_limited` | Calling get_latest_signal too fast | Increase `min_interval_seconds` or check cache |
| `hold: signal_expired` | Signal `valid_until` is in the past | Signal TTL too short, or clock skew |
| `hold: data_quality_degraded` | Upstream feed unhealthy | Check feed health in watchdog |
| `hold: low_confidence` | Signal confidence below threshold | Lower `confidence_threshold` or improve signals |
| `hold: high_risk` | Risk score ≥ 0.7 | Assess market conditions, may need to lower risk |
| `hold: safety_violation_*` | Envelope has wrong actionability | Check envelope creation — should never happen |
| `hold: registry_error` | SQLite query failed | Check DB path, permissions, disk space |
| `hold: bridge_error` | Unexpected exception | Check logs for traceback |

## Limitations

- Read-only: the bridge queries the registry but never writes
- Single-process: SQLite is not safe for concurrent writes from multiple processes
- Cache is in-memory only — lost on restart
- Rate limiting is per-bridge-instance — not distributed
- No WebSocket or real-time push — polling model only
- Strategy is a minimal skeleton — not production-hardened
- No short trades (`can_short = False`)

## Quick Start

```bash
# 1. Ensure signal intelligence layer is producing signals
python main.py  # starts signal producer

# 2. Verify signals in registry
python -c "from core.signals.registry import CanonicalSignalRegistry; r = CanonicalSignalRegistry(); print(r.query_latest(limit=5))"

# 3. Test bridge independently
python -c "
from core.signals.registry import CanonicalSignalRegistry
from integrations.freqtrade_bridge import FreqtradeBridge
r = CanonicalSignalRegistry()
b = FreqtradeBridge(r)
print(b.get_latest_signal('BTC/USDT'))
"

# 4. Configure Freqtrade to use AI4TradeSignalStrategy (dry-run only)
# See example config above
```