# Trading-Hub Integration Guide für Rainbow (Internal Read-Only)

**Ziel:** Rainbow als internen, read-only Signal-Provider in den trading-hub einbinden.

## Voraussetzungen

- ai4trade-bot Repo ist verfügbar (z.B. als Submodul, Clone neben trading-hub oder via Image).
- trading-hub verwendet Docker Compose (empfohlen: v2.20+ für `include`).
- Nur lesender Zugriff (`GET /signals/canonical/latest` etc.).
- Kein öffentlicher Port für Rainbow.

## 1. Empfohlene Architektur

```
trading-hub compose network
├── trading-hub (oder einzelne Bots)
├── rainbow          ← dieser Service
└── (optional) andere Services
```

- `trading-hub` spricht Rainbow intern als `http://rainbow:8000`
- Kein `ports:` Mapping für Rainbow im Production-Compose.

## 2. Integration per Docker Compose Include (empfohlen)

In deinem `docker-compose.yml` (oder `compose.yml`) im trading-hub Repo:

```yaml
include:
  - path: ./services/rainbow/rainbow.include.yml   # oder relativer Pfad zum ai4trade-bot
    # env_file: ...  # falls nötig
```

Oder direkt den Service inline einfügen (siehe unten).

## 3. Rainbow Service Definition (Copy-Paste)

Füge dies in dein Compose ein (oder in `services/rainbow/rainbow.include.yml`):

```yaml
services:
  rainbow:
    build:
      # Passe den Context an deine Struktur an:
      # - Submodul: ./ai4trade-bot
      # - Nebenliegend: ../ai4trade-bot
      # - Oder nutze ein vorgebautes Image
      context: ../ai4trade-bot
      dockerfile: rainbow.Dockerfile
    # WICHTIG: Kein ports: im Production-Setup!
    volumes:
      - rainbow_data:/app/rainbow/storage
      - ./config/rainbow.internal.yml:/app/rainbow/config.yaml:ro
    environment:
      RAINBOW_LOG_LEVEL: INFO
      RAINBOW_LOG_FORMAT: json
      # Weitere RAINBOW_* nur bei Bedarf
    restart: unless-stopped
    healthcheck:
      test:
        - CMD-SHELL
        - |
          python -c '
          import json, sys, time, pathlib
          p = pathlib.Path("/app/rainbow/storage/heartbeat_rainbow.json")
          if not p.exists(): sys.exit(1)
          data = json.loads(p.read_text())
          age = time.time() - data.get("timestamp_unix", 0)
          ok = data.get("status") in ("healthy", "running") and age < 120
          sys.exit(0 if ok else 1)
          '
      interval: 30s
      timeout: 10s
      start_period: 25s
      retries: 3
    networks:
      - trading_internal

volumes:
  rainbow_data:

networks:
  trading_internal:
    driver: bridge
```

## 4. Config Datei

Kopiere `docs/r4/rainbow.internal.yml` aus dem ai4trade-bot Repo nach `config/rainbow.internal.yml` (relativ zu deinem Compose).

Diese Config startet nur den TA-Collector (secret-frei) und ist für die erste Messphase optimiert.

## 5. Trading-Hub Client Konfiguration

Im trading-hub (oder den Bot-Containern) folgendes setzen:

```yaml
environment:
  - RAINBOW_URL=http://rainbow:8000
  # oder wie dein Client es erwartet
```

Der Client sollte folgende Endpoints nutzen (read-only):

- `GET /signals/canonical/latest?asset=BTC&limit=50`
- `GET /health`
- Optional: `/signals/latest`

Siehe Contract: `docs/integration/rainbow-signal-provider-contract.md`

**Wichtig:** Bei fehlendem Heartbeat oder nicht `healthy` Status → **fail-closed** behandeln.

## 6. Depends-on & Startup Order

```yaml
services:
  my-bot:
    ...
    depends_on:
      rainbow:
        condition: service_healthy
```

## 7. Standalone Testen (vor der Integration)

Bevor du in trading-hub einbindest, teste Rainbow standalone:

```bash
# Im ai4trade-bot Repo
docker compose -f docs/r4/standalone-rainbow.yml up -d

# Testen
curl http://localhost:18000/health
curl "http://localhost:18000/signals/canonical/latest?limit=5"
```

Sobald es stabil läuft, kannst du die Config und das Service-Fragment in trading-hub übernehmen.

## 8. Produktions-Hinweise

- **Niemals** Port 8000 nach außen mappen.
- Delivery-Worker bleibt `off`.
- Für die ersten 14 Tage nur TA-Collector.
- Monitoring über Heartbeat-Datei + `/health`.
- Bei Update des ai4trade-bot: Image neu bauen oder Context aktualisieren.

## 9. Rollback

Rainbow Service einfach aus dem Compose entfernen oder deaktivieren.
Client auf "unavailable" oder vorherigen Provider umstellen.

## Dateien zum Kopieren

Aus `ai4trade-bot/docs/r4/`:

- `rainbow.internal.yml` → `config/rainbow.internal.yml` (in trading-hub)
- `rainbow-compose-fragment.yml` oder `trading-hub/rainbow.include.yml` als Vorlage
- `standalone-rainbow.yml` nur zum lokalen Testen

## Verweise

- R3 Decision: `../reports/r3-fleet-reproducibility-decision-and-inventory-20260711.md`
- ADR: `../decisions/ADR-2026-07-11-hermes-fleet-r3-and-internal-rainbow-service.md`
- Contract: `../integration/rainbow-signal-provider-contract.md`
- Phase 0 Health: GREEN

Stand: 2026-07-11
