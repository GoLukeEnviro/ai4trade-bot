# R4 – Rainbow für trading-hub (Standalone + Integration)

Dieses Verzeichnis stellt alles bereit, damit Rainbow:

1. **Standalone** betrieben werden kann (zum Testen und Validieren).
2. **Einfach an den trading-hub** (https://github.com/GoLukeEnviro/trading-hub) angebunden werden kann.

## Wichtige Prinzipien

- **Internal only** — kein öffentlicher Port 8000
- Read-only für den trading-hub (nur GET auf `/signals/canonical/latest` etc.)
- TA-Collector als Baseline (secret-frei)
- Fail-closed bei Problemen (Heartbeat /health)
- Reproduzierbar und messbar

## 1. Standalone Betrieb (zum Testen)

Du kannst Rainbow komplett ohne trading-hub starten:

```bash
# Vom Root des ai4trade-bot Repos
docker compose -f docs/r4/standalone-rainbow.yml up -d

# Testen
curl http://localhost:18000/health
curl "http://localhost:18000/signals/canonical/latest?limit=10"
```

Datei: `standalone-rainbow.yml`

- Baut direkt aus dem aktuellen Repo.
- Nutzt `rainbow.internal.yml` als Config.
- Gibt Port 18000 für lokale Tests frei (nur Standalone!).
- Persistenz über Volume.

**Hinweis:** Im Standalone-Modus ist der Port nur für dich zum Testen freigegeben. Im trading-hub Setup darf **kein** Port exposed werden.

## 2. Anbindung an trading-hub

Siehe die dedizierte Anleitung:

→ **`trading-hub-integration.md`**

Zusammengefasst:

- `rainbow.internal.yml` nach `config/rainbow.internal.yml` (im trading-hub) kopieren.
- Service per `include` oder Copy-Paste einbinden (Beispiel in `trading-hub/rainbow.include.yml`).
- trading-hub Client auf `http://rainbow:8000` zeigen lassen.
- `depends_on` mit `condition: service_healthy`.
- Netzwerk teilen (z.B. `trading_internal`).

## Bereitgestellte Dateien

| Datei                              | Zweck |
|------------------------------------|-------|
| `standalone-rainbow.yml`           | Standalone Compose zum Testen |
| `rainbow.internal.yml`             | Minimale Config (TA only) |
| `trading-hub-integration.md`       | Vollständige Integrationsanleitung |
| `trading-hub/rainbow.include.yml`  | Fertiges Include für trading-hub Compose |
| `rainbow-compose-fragment.yml`     | Einfaches Fragment (falls kein include gewünscht) |
| `trading-hub-client-example.md`    | Beispiel-Code für den Client im trading-hub |
| `hermes-integration-checklist.md`  | Checkliste (älter, aber noch nützlich) |

## Schnell-Referenz für trading-hub

```yaml
# In deinem trading-hub Compose
include:
  - path: ./path/to/ai4trade-bot/docs/r4/trading-hub/rainbow.include.yml

services:
  my-bot:
    environment:
      - RAINBOW_URL=http://rainbow:8000
    depends_on:
      rainbow:
        condition: service_healthy
```

## Wichtige Regeln (unverhandelbar)

- Kein `ports:` für den rainbow Service im Production-Compose.
- Delivery Worker bleibt `off`.
- Erste 14 Tage Messung nur mit TA-Collector.
- Bei ungesundem Heartbeat oder /health → fail-closed im Client.

## Nächste Schritte

1. Standalone testen (`standalone-rainbow.yml`)
2. Config und Include in trading-hub übernehmen
3. Client verdrahten
4. 14+ Tage stabile Messung (R7)
5. Danach entscheiden, ob weitere Collector/Evaluation aktiviert werden

## Verweise

- R3 Decision & Inventory: `../reports/r3-fleet-reproducibility-decision-and-inventory-20260711.md`
- ADR: `../decisions/ADR-2026-07-11-hermes-fleet-r3-and-internal-rainbow-service.md`
- Contract: `../integration/rainbow-signal-provider-contract.md`
- Phase 0 Health Audit (GREEN)

Stand: 2026-07-11

