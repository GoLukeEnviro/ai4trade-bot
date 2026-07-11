# R4 – Internal Rainbow Service Definition for HermesTrader Compose

**Status:** Ready for copy-paste into HermesTrader root compose  
**Date:** 2026-07-11  
**Based on:** R3 Fleet Reproducibility Decision + Phase 0 GREEN baseline

## Ziel

Bereitstellung eines **internen, read-only** Rainbow Services als Sidecar für die Trading-Hub Bots auf HermesTrader.

**Harte Constraints (nicht verhandelbar):**
- Kein öffentlicher Port (kein `ports:` für Rainbow)
- Nur lesender Zugriff über den Trading-Hub Consumer
- TA-Collector als Baseline (keine Secrets nötig für den Start)
- Fail-closed bei ungesunden/stale Signalen
- Delivery Worker bleibt `off`

## Empfohlene Service-Definition (Copy-Paste)

Füge diesen Block in euer HermesTrader Compose (z.B. `docker-compose.yml` oder `compose.rainbow.yml`) ein.

```yaml
  rainbow:
    build:
      context: ./ai4trade-bot          # oder Pfad zum geklonten Repo
      dockerfile: rainbow.Dockerfile
    # WICHTIG: Kein ports: Mapping nach außen!
    # Der Service ist nur über das interne Compose-Netz erreichbar.
    volumes:
      # Empfohlene Config-Montage (löst das rainbow/config.yaml Problem):
      # Entweder die Datei direkt mounten ODER sicherstellen, dass im Kontext
      # rainbow/config.yaml existiert.
      - ./ai4trade-bot/rainbow/config/rainbow.internal.yml:/app/rainbow/config.yaml:ro
      - rainbow_storage:/app/rainbow/storage
    environment:
      # Für Baseline (TA + öffentliche APIs) reicht das meist aus.
      # Weitere RAINBOW_* nur bei Bedarf für zusätzliche Collector.
      - RAINBOW_LOG_LEVEL=INFO
      - RAINBOW_LOG_FORMAT=json
    restart: unless-stopped
    healthcheck:
      # Bevorzugt die Datei-basierte Prüfung (passt zum Dockerfile HEALTHCHECK)
      test:
        - CMD-SHELL
        - |
          python -c "
          import json, sys, time, pathlib
          p = pathlib.Path('/app/rainbow/storage/heartbeat_rainbow.json')
          if not p.exists():
              sys.exit(1)
          data = json.loads(p.read_text())
          age = time.time() - data.get('timestamp_unix', 0)
          sys.exit(0 if age < 120 and data.get('status') in ('healthy', 'running') else 1)
          "
      interval: 30s
      timeout: 10s
      start_period: 20s
      retries: 3
    networks:
      - hermes_internal
    # Optional: Ressourcen-Limits für Stabilität
    # deploy:
    #   resources:
    #     limits:
    #       cpus: '1.0'
    #       memory: 512M
```

## Config-Empfehlung (rainbow.internal.yml)

Erstelle im HermesTrader-Repo (oder mountbar) eine Datei mit folgendem Inhalt:

```yaml
# rainbow/config/rainbow.internal.yml
# Für HermesTrader R4/R7 Baseline – minimal & secret-frei

log_level: INFO
log_format: json

db_path: rainbow/storage/signals.db

market_data:
  bitget_base_url: https://api.bitget.com
  coingecko_base_url: https://api.coingecko.com/api/v3
  default_interval: 1h
  default_candle_limit: 200

api:
  host: 0.0.0.0
  port: 8000

scorer:
  weights:
    technical: 0.4
    sentiment: 0.3
    social: 0.2
    news: 0.1

collectors:
  ta:
    enabled: true
    interval_seconds: 60
    assets:
      - BTC
      - ETH
      - SOL
    params:
      timeframes:
        - 1h
        - 4h

  # Alle weiteren Collector für R7-Baseline bewusst deaktiviert
  # twitter:
  #   enabled: false
  # reddit:
  #   enabled: false
  # news:
  #   enabled: false

evaluation:
  enabled: false   # Erst nach R7-Messung wieder aktivieren
```

## Verwendung durch Trading-Hub Container

Im Trading-Hub Service (im selben Compose):

```yaml
  trading-hub:
    ...
    environment:
      - RAINBOW_INTERNAL_URL=http://rainbow:8000
    depends_on:
      rainbow:
        condition: service_healthy
    networks:
      - hermes_internal
```

Der Read-Only Client sollte dann `RAINBOW_INTERNAL_URL/signals/canonical/latest` nutzen.

## Health & Observability

- Heartbeat-Datei: `/app/rainbow/storage/heartbeat_rainbow.json` (im Volume)
- HTTP: `http://rainbow:8000/health`
- Watchdog auf HermesTrader-Seite sollte beide Quellen prüfen können.

## Rollback / Deaktivierung

Einfach den `rainbow` Service aus dem Compose entfernen oder deaktivieren.  
Trading-Hub muss `UNAVAILABLE` behandeln und fail-closed gehen (bereits im Contract vorgesehen).

## Nächste Schritte nach diesem Service

1. In das HermesTrader Compose einbauen (R4).
2. Trading-Hub read-only Client gegen `http://rainbow:8000` verdrahten.
3. 14+ Tage Messung (R7) starten.
4. Danach anhand realer Daten entscheiden, ob mehr Collector, Evaluation etc. aktiviert werden.

## Quellen

- R3 Decision: `docs/reports/r3-fleet-reproducibility-decision-and-inventory-20260711.md`
- ADR: `docs/decisions/ADR-2026-07-11-hermes-fleet-r3-and-internal-rainbow-service.md`
- Phase 0 Health Audit (GREEN)
- `rainbow.Dockerfile` + `rainbow/main.py` + `core/heartbeat_writer.py`

---

**Hinweis:** Diese Definition wurde bewusst so gestaltet, dass sie **keine** Änderung am ai4trade-bot Code erfordert. Sie ist nur Dokumentation + Copy-Paste für den HermesTrader Compose.
