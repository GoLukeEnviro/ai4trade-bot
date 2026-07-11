# Phase 0 — Rainbow Runtime Health and Evidence Export Audit

**Date:** 2026-07-11  
**Repo:** GoLukeEnviro/ai4trade-bot  
**Upstream consumer:** GoLukeEnviro/trading-hub  
**Verdict:** **GREEN** (observable, read-only health checks available)

---

## 1. Runtime Inventory

| Component | Process | Health surface | Data paths |
|-----------|---------|----------------|------------|
| Legacy CLI | `main.py` | `storage/heartbeat.json` | `storage/*.jsonl`, config YAML |
| Rainbow FastAPI | `rainbow/main.py` | `storage/heartbeat_rainbow.json`, `GET /health` | SQLite signal store, `storage/` |
| Watchdog | `core/watchdog.py` | Monitors heartbeat files | `config/watchdog.json` |
| Delivery worker | `rainbow/delivery/` | Default `off` — no runtime impact | Outbox DB when enabled |

**Ports (Rainbow):** FastAPI via uvicorn (config-driven).  
**Secrets:** `.env` / env vars — never logged by health tooling.

---

## 2. Healthcheck Method (read-only)

### File-based (preferred for Docker)

```bash
python -m core.healthcheck_cmd
```

Checks: file exists → valid JSON → `timestamp_unix` present → age ≤ 120s → status ∈ `{healthy, running}`.

### HTTP (Rainbow only)

```bash
curl -s http://<host>:<port>/health
```

Returns collector status and store metrics. Read-only — no mutation.

### Watchdog matrix

| Condition | Severity |
|-----------|----------|
| Heartbeat missing | CRITICAL |
| Malformed JSON | CRITICAL |
| Stale (>120s default) | WARNING |
| Status not healthy/running | WARNING |

---

## 3. Evidence Export Method (summary)

Preferred read-only path for Phase 0:

1. **Fixture pack** — `docs/integration/fixtures/rainbow-signals/` (synthetic, always safe)
2. **API read** — `GET /signals/canonical/latest`, `GET /signals/latest` (live, requires running Rainbow)
3. **Heartbeat** — `storage/heartbeat_rainbow.json` or fixture `heartbeat.json`

Full spec: `docs/integration/rainbow-signal-evidence-export.md` (Issue #57).

---

## 4. Redaction Rules

| Rule | Enforcement |
|------|-------------|
| No API keys in exports | Fixtures synthetic; API must not echo secrets |
| `raw_data` redacted in canonical path | Contract § redaction policy |
| `redaction_status` field required in export schema | Fixture pack + validator |

---

## 5. GREEN / YELLOW / RED Matrix

| Check | Verdict | Condition |
|-------|---------|-----------|
| Heartbeat file fresh + valid | **GREEN** | Legacy or Rainbow process alive |
| Heartbeat stale (>120s) | **YELLOW** | Process may be hung |
| Heartbeat missing/malformed | **RED** | No safe observability |
| `/health` returns 200 | **GREEN** | Rainbow API up |
| Signal evidence via fixtures | **GREEN** | Always available offline |
| Live API evidence | **YELLOW** | Requires running instance |
| Delivery worker `live` | **RED** for Phase 0 | Out of scope — must stay `off` |

**Current baseline verdict: GREEN** — heartbeat + health endpoints + fixture evidence are documented and testable without runtime mutation.

---

## 6. Remediation (approval-gated, not Phase 0 blockers)

| Gap | Issue | Gate |
|-----|-------|------|
| Automated evidence export CLI | #57 spec done; runtime CLI later | User approval |
| Metadata completeness automation | #58 checker | Fixture phase complete |
| VPS deployment health | HermesTrader ops | Separate infra track |

---

## 7. References

- Implementation report: `docs/reports/runtime-health-watchdog-report.md`
- Contract: `docs/integration/rainbow-signal-provider-contract.md`
- Watchdog config: `config/watchdog.json`
- Heartbeat writer: `core/heartbeat_writer.py` (Windows fix #73)