# Rainbow Signal Evidence Export Method

> **Status:** Phase 0 spec — read-only design  
> **Issue:** #57  
> **Depends on:** #51 (contract), #52 (health), #56 (fixtures)

---

## 1. Evidence Source Candidates

| Source | Access | Safety | Phase 0 |
|--------|--------|--------|---------|
| Fixture pack | `docs/integration/fixtures/rainbow-signals/*.json` | Synthetic, offline | **Preferred** |
| Canonical API | `GET /signals/canonical/latest` | Read-only HTTP | Secondary (needs running Rainbow) |
| Signal API | `GET /signals/latest` | Read-only HTTP | Secondary |
| Heartbeat file | `storage/heartbeat_rainbow.json` | File read | Health evidence only |
| SQLite store | Rainbow signal DB | Direct file access | Not recommended (coupling) |
| Logs | Application stdout | Parse | Redaction risk — avoid |

**Selected method:** Fixture pack for CI/contract validation; live API for operational review when Rainbow is running.

---

## 2. Sanitized Export Schema

Uses the contract export format (see fixtures README):

```json
{
  "schema_version": 1,
  "event_type": "signal",
  "source_system": "rainbow",
  "source_id": "rainbow:ta",
  "strategy_id": "rainbow_v1",
  "model_id": null,
  "symbol": "BTC/USDT:USDT",
  "timeframe": "1h",
  "timestamp_utc": "2026-06-10T12:00:00Z",
  "emitted_at_utc": "2026-06-10T12:00:02Z",
  "direction": "long",
  "confidence": 0.85,
  "signal_strength": 0.72,
  "regime_hint": null,
  "metadata": {},
  "redaction_status": "clean"
}
```

---

## 3. Redaction Rules

| Data class | Rule |
|------------|------|
| API keys / tokens | Never export — strip from `raw_data` |
| Private keys | Exclude |
| PII | Not collected in Rainbow signals |
| `raw_data` | Redact or omit in canonical export |
| `redaction_status` | Must be `clean`, `redacted`, or `unchecked` |

---

## 4. Stale / No-Signal Behavior

| Case | `event_type` | Consumer action |
|------|--------------|-----------------|
| Active signal | `signal` | Validate + use if fresh |
| No opportunity | `no_signal` | Log, do not trade |
| System alive, no trade signal | `heartbeat` | Health only |
| Stale `data_quality.status` | `signal` | **WARN** — reject for decisions |
| Missing required fields | — | **FAIL** validation |

Reference fixtures: `stale_signal.json`, `no_signal.json`, `heartbeat.json`.

---

## 5. Failure Behavior (GREEN / YELLOW / RED)

| Situation | Verdict |
|-----------|---------|
| Fixture validates | **GREEN** |
| API returns 200 + valid envelopes | **GREEN** |
| API unreachable | **YELLOW** — fall back to fixtures |
| Stale signal in response | **YELLOW** — schema OK, semantically stale |
| Malformed JSON / missing required fields | **RED** |
| Secrets detected in export | **RED** |

---

## 6. Out of Scope (Phase 0)

- Scheduled export cron
- S3/archive pipeline
- Webhook streaming
- Runtime activation without approval

---

## 7. Deliverable Checklist

- [x] Evidence sources documented
- [x] Preferred export method selected (fixtures + API)
- [x] Sanitized schema defined
- [x] Redaction rules explicit
- [x] Stale/failure behavior defined