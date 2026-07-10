# AI4Trade Delivery Worker

The optional delivery worker transports already evaluated Rainbow signals to
AI4Trade. It is deliberately separate from `RainbowEngine`: Rainbow remains a
credential-free, read-only provider at `http://127.0.0.1:8000` and continues to
offer only `GET /health` and `GET /signals/latest`.

Run the worker with:

```bash
python -m rainbow.delivery
```

## Modes and configuration

`AI4TRADE_DELIVERY_MODE` defaults to `off`.

- `off` does not read Rainbow or send external requests.
- `shadow` reads and evaluates signals, then records delivery evidence in the
  SQLite outbox without loading an AI4Trade token or sending a request.
- `live` is the only mode which creates an AI4Trade client. It requires
  `AI4TRADE_TOKEN`.

The worker reads only the local Rainbow endpoint configured by
`AI4TRADE_DELIVERY_PROVIDER_URL` (default `http://127.0.0.1:8000`). Its durable
outbox is configured with `AI4TRADE_DELIVERY_OUTBOX_PATH` (default
`storage/ai4trade_delivery.db`).

Assets are denied by default. Each permitted route must provide an explicit
AI4Trade symbol and quantity through `AI4TRADE_DELIVERY_ASSET_ROUTES`, for
example:

```json
{"BTC": {"symbol": "BTCUSDT", "quantity": 0.001}}
```

Only fresh technical signals may be delivered. The maximum age is controlled by
`AI4TRADE_DELIVERY_MAX_AGE_SECONDS` (default 900). A signal must have a numeric,
positive price in its own `value`; social, news and LLM values are never treated
as a price. Delivery actions follow the legacy-compatible BUY/SELL/HOLD policy,
while Rainbow's `canonical_symbol` remains reserved for the Trading-Hub contract.

The outbox records `pending`, `retrying`, `sent`, and `dead_letter` entries using
a delivery fingerprint. Authentication and non-retryable failures degrade only
the worker; they do not affect the Rainbow producer or Trading Hub.

## Operational boundary

Enabling a mode, supplying tokens, installing a supervisor, and changing any
runtime deployment remain separate approval-gated operations. The intended
rollout is `off` → seven days `shadow` → a BTC transport-only canary → wider
delivery. It is not a Trading-Hub live-trading canary.
