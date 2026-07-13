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

# Rainbow API testen
curl http://localhost:18080/health
curl "http://localhost:18080/signals/canonical/latest?limit=10"

# Dashboard (Browser)
# http://localhost:18081

# Automatisierter Smoke-Test (Linux/VPS)
bash docs/r4/smoke-test.sh
```

Datei: `standalone-rainbow.yml`

- Baut direkt aus dem aktuellen Repo.
- Nutzt `rainbow.internal.yml` als Config.
- Rainbow API: Port `18080` (nur Standalone!).
- Test-Dashboard: Port `18081` (nginx + Vanilla JS).
- Persistenz über Volume.

**Hinweis:** Im Standalone-Modus sind die Ports nur für Tests freigegeben. Im trading-hub Setup darf **kein** Port exposed werden.

### Test auf HermesTrader VPS

```bash
ssh hermestrader-root
mkdir -p /opt/rainbow-test && cd /opt/rainbow-test
git clone --depth 1 https://github.com/GoLukeEnviro/ai4trade-bot.git .
bash docs/r4/smoke-test.sh
# Dashboard: http://100.96.132.39:18081 (Tailscale)
```

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
| `standalone-rainbow.yml`           | Standalone Compose (Rainbow + Dashboard) |
| `dashboard/`                       | Minimales Test-Dashboard (nginx + HTML/JS) |
| `smoke-test.sh`                    | Automatisierter Standalone-Smoke-Test |
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


## Database Volumes

SQLite live databases are runtime state and must never be committed to this repository. In Docker deployments, `signals.db`, `signal_outcomes.db`, WAL files, and archive data live in Docker volumes so restarts can preserve state without mixing production data into source control. Keep local database files out of Git and mount the configured database paths as volumes in compose files.
