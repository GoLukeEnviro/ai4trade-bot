# HermesTrader – Rainbow Internal Integration Checklist

## Voraussetzungen
- [ ] Fleet Decision getroffen (freqforge + freqforge-canary empfohlen)
- [ ] R3 ADR akzeptiert
- [ ] ai4trade-bot auf einem stabilen Commit (z.B. nach Hygiene)

## Vorbereitung auf HermesTrader
- [ ] `docs/r4/rainbow.internal.yml` nach `config/rainbow.internal.yml` kopieren
- [ ] `docs/r4/rainbow-compose-fragment.yml` oder `example-compose.rainbow-only.yml` als Basis verwenden
- [ ] Volume-Pfade und Context anpassen
- [ ] Sicherstellen, dass `rainbow` Service **keinen** public Port hat

## Compose & Networking
- [ ] Rainbow im gleichen internen Netz wie Trading-Hub Services
- [ ] Healthcheck auf Heartbeat-Datei oder `/health` aktiv
- [ ] Trading-Hub Service hängt von `rainbow` mit `condition: service_healthy` ab

## Trading-Hub Client Konfiguration
- [ ] `RAINBOW_INTERNAL_URL=http://rainbow:8000` (oder Service-Name)
- [ ] Client verwendet `/signals/canonical/latest`
- [ ] Stale / unhealthy → fail-closed behandeln

## Erster Start (ohne Live-Trading)
- [ ] Nur Rainbow hochfahren und Health prüfen
- [ ] `GET /health` und Heartbeat-Datei validieren
- [ ] `GET /signals/canonical/latest` gibt Antwort (auch wenn leer)

## Messung (R7)
- [ ] Mindestens 14 Tage stabile Laufzeit
- [ ] Heartbeat + canonical Signals regelmäßig prüfen
- [ ] Evidenz sichern (keine Mutation)

## Rollback
- [ ] Rainbow Service einfach aus Compose entfernen
- [ ] Trading-Hub Client auf Fallback oder "unavailable" umstellen

Fertig für R4 → R7 Messung.
