# ADR-2026-07-11: B→C Delivery Worker — Isoliert von Trading-Hub

> **Status:** Accepted
> **Datum:** 2026-07-11
> **Kontext:** PR #66 Reconciliation, Trading-Hub #489, #423

## Entscheidung

Der B→C-Migrationspfad für AI4Trade-Legacy-Transport wird als **isolierter Delivery-Worker** (`rainbow/delivery/`) implementiert — nicht als in-engine `rainbow/adapters/`-Integration.

PR #66 wird **nicht monolithisch gemergt**, sondern in drei fokussierte PRs aufgeteilt. Der `canonical_symbol`-Anteil wird **verworfen**.

## Kontext

Zwei orthogonale Integrationspfade existieren:

| Pfad | Consumer | Autorität |
|------|----------|-----------|
| **Trading-Hub advisory** | `si_v2/rainbow/client.py` (GET-only) | Issue #489, R1–R6 merged |
| **B→C Legacy-Transport** | `rainbow/delivery/` → AI4Trade API | Dieser ADR |

Trading-Hub #489 und Live-Roadmap #423 autorisierten **kein** Live-Trading und **keinen** Rainbow-Execution-Pfad. Der Delivery-Worker ist ein **Legacy-Ersatz** für `main.py`/`adapters/signal_publisher.py` — nicht Teil des Trading-Hub-Trackers.

## Begründung

1. **Credential-Isolation:** Rainbow bleibt credential-free; Token nur im separaten Worker-Prozess (`live`-Mode).
2. **Trading-Hub-Kompatibilität:** R2 (#498) nutzt `asset`-Feld direkt auf dem canonical endpoint — kein `metadata.canonical_symbol`-Lookup (`test_no_pr66_canonical_symbol_inference`).
3. **Besseres Rollout-Modell:** `off` → `shadow` (7 Tage Evidence) → `live` (approval-gated) ohne Producer-Mutation.
4. **Supersedes in-engine adapters:** Der ursprüngliche Plan (`.omo/plans/rainbow-ai4trade-migration-plan.md` Phase A/B) wird durch den isolierten Worker ersetzt.

## Konsequenzen

### Implementiert

- `rainbow/delivery/` — Worker, Outbox, Policy, Client (default `off`)
- `docs/integration/ai4trade-delivery-worker.md` — Betriebsdoku
- `rainbow.Dockerfile` — `COPY core ./core` (Rainbow importiert `core.*`)

### Verworfen (aus PR #66)

- `rainbow/symbols.py` und `metadata.canonical_symbol`
- `core/signals/adapters.py`-Änderungen für canonical symbol mapping
- Trading-Hub Companion-PR #488 (bereits geschlossen, durch R2 superseded)

### Explizit ausgeschlossen

- Token-, Supervisor-, Compose- oder VPS-Änderungen
- Trading-Hub Execution-Pfad, Freqtrade-Orders, RiskGuard-Bypass
- D1/D2-Freigabe via #423 (unverändert blockiert)
- R7 Dry-Run-Messung (Host-Operator-Aufgabe, kein Code)

## Verifikation

- `AI4TRADE_DELIVERY_MODE=off` als Default — kein Verhaltenswechsel bei Merge
- Guard-Tests in Trading-Hub bleiben unverändert grün
- Bandit/pip-audit/ruff/pytest grün auf Python 3.11 und 3.12