**ARCHIVIERT** — Stand 2026-06-09. Die meisten Items sind erledigt oder wurden als Tech-Debt in `whats-next.md` übertragen. Siehe `CHANGELOG.md` für den aktuellen Feature-Stand.

---

# P2 Cleanup Plan — ai4trade-bot

## Stand: 2026-06-09 | master @ 04cd50d
## Tests: 824 | Ruff: 0 | P1s: done | Features: complete

---

## P2-Audit: Alle Findings kategorisiert

### Batch 1 — Test Coverage Gaps (15 Module ohne dedizierte Tests)

| # | Module | Risiko | Aufwand | Priorität |
|---|--------|--------|---------|-----------|
| P2-1 | `rainbow/collectors/news_collector.py` | Mittel | Klein | Hoch |
| P2-2 | `rainbow/collectors/reddit_collector.py` | Mittel | Klein | Hoch |
| P2-3 | `rainbow/collectors/ta_collector.py` | Mittel | Klein | Hoch |
| P2-4 | `rainbow/collectors/twitter_collector.py` | Mittel | Klein | Hoch |
| P2-5 | `rainbow/collectors/base.py` | Niedrig | Klein | Mittel |
| P2-6 | `rainbow/evaluation/context_enricher.py` | Mittel | Mittel | Hoch |
| P2-7 | `rainbow/evaluation/cache.py` | Mittel | Klein | Hoch |
| P2-8 | `rainbow/evaluation/base.py` | Niedrig | Klein | Mittel |
| P2-9 | `rainbow/processor/scorer.py` | Mittel | Mittel | Hoch |
| P2-10 | `rainbow/processor/store.py` | Hoch (SQLite+async) | Mittel | Hoch |
| P2-11 | `rainbow/distribution/metrics.py` | Niedrig | Klein | Niedrig |
| P2-12 | `rainbow/market_data/coingecko.py` | Mittel | Klein | Mittel |
| P2-13 | `rainbow/exceptions.py` | Sehr niedrig | Minimal | Niedrig |
| P2-14 | `core/predictive.py` | Niedrig | Klein | Niedrig |
| P2-15 | `integrations/primoagent_bridge.py` | Mittel | Mittel | Mittel |

**Empfehlung:** Batch als einzelner PR `test: add coverage for untested rainbow/core modules`.

---

### Batch 2 — Technical Debt

| # | Finding | Quelle | Risiko | Priorität |
|---|---------|--------|--------|-----------|
| P2-16 | **Registry/DB wächst unbounded** — kein Cleanup, kein Vacuum, kein TTL | MVP-Report L191 | Hoch | Hoch |
| P2-17 | **Confidence Modulation nicht in Bridge verdrahtet** — existiert als Modul, wird aber von niemandem konsumiert | Modulation Report | Mittel | Hoch |
| P2-18 | **Outcome Tracker: kein Background-Scheduling** — CLI-only, muss manuell/cron gestartet werden | Outcome Report | Mittel | Mittel |
| P2-19 | **Outcome Tracker: kein Heartbeat-Integration** — Daemon-Modus hat kein Lifecycle-Signal | Outcome Report | Niedrig | Mittel |
| P2-20 | **Outcome Tracker: StaticPriceProvider returnt 0.0** — braucht echten Price-Feed | Outcome Report | Mittel | Mittel |
| P2-21 | **LLM Evaluator: Ollama-Fallback nicht implementiert** — Single-Provider-Abhängigkeit (DeepSeek) | LLM Report | Mittel | Niedrig |
| P2-22 | **LLM Evaluator: CryptoSignal-Felder nicht im Prompt** — timeframe/stop_loss/take_profit/leverage nicht an LLM übergeben | LLM Report | Niedrig | Niedrig |
| P2-23 | **Derivatives Adapter: Feature Flag als Klassenattribut** — nicht runtime-configurable | Derivatives Report | Niedrig | Niedrig |
| P2-24 | **Derivatives Adapter: nicht in Canonical Envelope/RiskGate integriert** | Derivatives Report | Mittel | Mittel |
| P2-25 | **Freqtrade Bridge: Cache nur in-memory** — verloren bei Restart | Bridge Report | Niedrig | Niedrig |
| P2-26 | **Freqtrade Bridge: Rate-Limiting nur per-Instance** — nicht verteilt über Prozesse | Bridge Report | Niedrig | Niedrig |

---

### Batch 3 — Infrastructure / Ops

| # | Finding | Risiko | Priorität |
|---|---------|--------|-----------|
| P2-27 | **Config-Version 27→28 Validierung** — Hermes-Orchestrator-Profil | Niedrig | Mittel |
| P2-28 | **Gateway-Status-Entscheidung** — seit Mai gestoppt, Architektur-Frage | Niedrig | Niedrig |
| P2-29 | **Polymarket-Fadi Profil** — Stub, Keep/Archive/Delete klären | Sehr niedrig | Niedrig |
| P2-30 | **Docker Heartbeat Verify (#29)** — Environment-Test, nur wo Docker verfügbar | Niedrig | Niedrig |

---

## Empfohlene P2-Batches (PRs)

### PR #45: Test Coverage — Rainbow Collectors + Evaluation (P2-1 bis P2-10)

```
Scope:
  - rainbow/collectors/ (4 Collector + Base)
  - rainbow/evaluation/ (cache, context_enricher, base)
  - rainbow/processor/ (scorer, store)

  ~10 neue Test-Files
  Ziel: alle rainbow-Module mit Tests abgedeckt
```

### PR #46: Registry Rotation + DB Cleanup (P2-16)

```
Scope:
  - core/signals/registry.py: add cleanup_expired() + vacuum()
  - core/outcomes/repository.py: add cleanup_old() + vacuum()
  - Optionaler CLI-Command: python -m core.db_maintenance --vacuum
  - Tests für Rotation

  Ziel: DB-Wachstum kontrollierbar, keine unbounded Files
```

### PR #47: Confidence Modulation → Bridge Wiring (P2-17)

```
Scope:
  - integrations/freqtrade_bridge.py: consume ModulatedConfidence
  - ConfidenceModulator wird Teil der Bridge-Pipeline
  - Fallback: wenn Modulation nicht verfügbar, direkte Confidence nutzen
  - Tests für integrierte Pipeline

  Ziel: Bridge nutzt modulierte Confidence statt raw
  Safety: final_confidence ≤ raw_confidence, HOLD bleibt HOLD
```

### PR #48: Outcome Tracker Scheduling (P2-18, P2-19)

```
Scope:
  - core/outcome_tracker.py: add --interval N / --daemon mode
  - Heartbeat-Integration: write heartbeat while running
  - Tests für Scheduling-Logic

  Ziel: outcome_tracker kann als Daemon laufen
```

### PR #49: Remaining Small Debt (P2-20 bis P2-26)

```
Scope:
  - StaticPriceProvider → Exchange-Price-Fetcher Stub
  - Derivatives Adapter: runtime-configurable feature flag
  - Freqtrade Bridge: persist cache option (optional)

  Ziel: kleine Items aufräumen
```

### PR #50: Infrastructure Cleanup (P2-27 bis P2-30)

```
Scope:
  - Config version validation script
  - Polymarket-Fadi decision dokumentiert
  - #29 Docker Heartbeat Verify (nur in Docker-Umgebung)

  Ziel: Ops-Schulden dokumentieren und wo möglich bereinigen
```

---

## Was NICHT in P2 gehört

- **#25 Secondary Review** — Nicht P2-Cleanup, sondern eigenes Feature. Separate Entscheidung.
- **Ollama Fallback (P2-21)** — Architektur-Entscheidung, kein Cleanup. Wenn gewollt, als eigener PR.
- **Live Derivatives** — Komplett außer Scope. Braucht Exchange-Credentials.
- **ML Training Pipeline** — Komplett außer Scope. Braucht Safety-Review.

---

## Reihenfolge-Empfehlung

```
PR #45  Test Coverage (sicherster PR, kein Prod-Code-Change)
PR #46  Registry Rotation (wichtigstes Debt-Item)
PR #47  Confidence → Bridge Wiring (funktionales P2)
PR #48  Outcome Scheduling (ops-nützlich)
PR #49  Remaining Small Debt (Aufräumen)
PR #50  Infrastructure Cleanup (Doku + Ops)
```

PR #45 und #46 können **parallel** gebaut werden (keine Abhängigkeit).
PR #47 hängt nicht von #45/#46 ab, aber sollte **nach** #46 kommen (nutzt Registry).

---

## Geschätzter Gesamtaufwand

| PR | Neue Tests | Prod-Changes | Risiko |
|----|-----------|-------------|--------|
| #45 | ~40-60 | 0 (nur Tests) | Minimal |
| #46 | ~10-15 | Registry+Repo | Niedrig |
| #47 | ~15-20 | Bridge | Mittel |
| #48 | ~10-15 | Tracker | Niedrig |
| #49 | ~10-15 | Diverse | Niedrig |
| #50 | ~5-10 | Doku/Scripts | Minimal |
| **Total** | **~90-135** | | |
