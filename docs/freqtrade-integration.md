# Freqtrade Integration Guide

This guide explains how to connect a Freqtrade bot to the Rainbow Intelligence Engine for signal consumption.

## Architecture

```
Rainbow Intelligence Engine (port 8000)
  │
  ├── GET /signals/latest?pair=BTCUSDT  ← Freqtrade polls this
  │
  └── POST /signals/ingest               ← Legacy strategy pushes here
```

## Prerequisites

- Running Rainbow Intelligence Engine (see `rainbow/main.py`)
- Freqtrade instance (dry-run mode recommended)
- Network connectivity between Freqtrade and Rainbow Engine

## Setup

### 1. Configure Rainbow Engine URL

Set the environment variable in your Freqtrade environment:

```bash
export RAINBOW_API_URL=http://your-rainbow-host:8000
```

Or edit the `FreqtradeSignalBridge` constructor directly.

### 2. Install the Strategy

Copy the strategy file to your Freqtrade strategies directory:

```bash
cp integrations/freqtrade_strategy.py \
   /path/to/freqtrade/user_data/strategies/rainbow_signal_strategy.py
```

### 3. Configure Freqtrade

In your Freqtrade config (`config.json`):

```json
{
  "strategy": "RainbowSignalStrategy",
  "dry_run": true,
  "stake_currency": "USDT",
  "exchange": {
    "name": "binance",
    "pair_whitelist": ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
  }
}
```

### 4. Start Freqtrade

```bash
freqtrade trade --config config.json --strategy RainbowSignalStrategy
```

## Confidence Thresholds

| Threshold | Behavior |
|-----------|----------|
| ≥ 80 | Strong signal — high conviction entry |
| 65-79 | Standard entry (default threshold) |
| 50-64 | Weak signal — skipped by default |
| < 50 | No entry |

Configure via environment:

```bash
export CONFIDENCE_THRESHOLD=65   # Minimum confidence to enter
export AI_CONFIDENCE_MIN=0.3     # Minimum AI confidence
```

## Signal Format

The Rainbow Engine returns signals via `GET /signals/latest`:

```json
{
  "signal_id": "uuid",
  "asset": "BTCUSDT",
  "direction": "bullish",
  "confidence": 0.78,
  "strength": 0.82,
  "rainbow_score": 0.75,
  "ai_evaluation": {
    "ai_confidence": 0.85,
    "risk_level": "medium",
    "recommended_action": "enter"
  }
}
```

The `FreqtradeSignalBridge` translates:
- `direction: bullish` → `BUY`
- `direction: bearish` → `SELL`
- `direction: neutral` → `HOLD`

## Graceful Fallback

- If Rainbow Engine is unreachable → returns `HOLD` (no trade)
- Rate limited to 1 request/second per pair
- 2-second timeout, cached signal used during rate limit cooldown
- No impact on Freqtrade operation if Rainbow is down

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Connection refused" | Check Rainbow Engine is running on configured URL |
| All signals are HOLD | Check `CONFIDENCE_THRESHOLD` and signal quality |
| Rate limit warnings | Increase `min_request_interval` in bridge constructor |
| Import errors | Ensure ai4trade-bot is in Python path |

## Safety Notes

- **Always start in dry-run mode** — observe signal quality for 48-72h
- Never set `dry_run: false` without explicit approval
- The strategy uses trailing stops and 5% stop loss by default
- Review signal outcomes in the `signal_outcomes` SQLite table
