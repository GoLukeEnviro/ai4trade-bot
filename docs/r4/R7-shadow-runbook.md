# R7 – 14-Tage Shadow Validation und Release Gate

Diese Anleitung startet **keinen** Live-Handel. Rainbow bleibt ein interner,
read-only Signal-Provider; Canonical Envelopes müssen `can_execute: false` und
`dry_run_only: true` behalten. Ohne einen benannten HermesTrader-Zielhost,
Zugang und dessen Compose-Kontext wird keine Remote-Änderung durchgeführt.

## 1. Verbindliche Ausgangsbasis

Auf der Zielumgebung nur fast-forward aktualisieren:

```bash
git fetch origin --prune
git switch master
git pull --ff-only origin master
git rev-parse HEAD
git status --short
```

Die Arbeitskopie muss sauber sein. Der bekannte Ausgangsstand ist
`710e4a638c286d514d9b1eeec571bda73c03f715` oder ein späterer, bereits
überprüfter `master`-Commit. Vor dem Start in GitHub die Checks dieses
tatsächlichen Commits prüfen: **backtest**, **lint**, **security**, **test
(3.11)** und **test (3.12)** müssen jeweils erfolgreich sein.

## 2. R7-Sicherheitskonfiguration

Die versionierte Datei [`rainbow.internal.yml`](rainbow.internal.yml) ist die
verbindliche R7-Baseline und wird im HermesTrader-Compose schreibgeschützt nach
`/app/rainbow/config.yaml` gemountet.

| Komponente | R7-Einstellung |
| --- | --- |
| TA | aktiv, 60 Sekunden, BTC/ETH/SOL, 1h/4h |
| Derivatives | installiert, aber `enabled: false` |
| LLM Evaluation und Critic | beide `enabled: false` |
| XGBoost | kein trainiertes Modell ausliefern; der Scorer bleibt beim deterministischen Fallback |
| Delivery | `AI4TRADE_DELIVERY_MODE=off` |
| trading-hub | nur `GET /health`, `GET /metrics`, `GET /signals/canonical/latest`; kein öffentlicher Rainbow-Port |

Die bereitgestellten Compose-Fragmente setzen Delivery explizit auf `off`.
Eine Aktivierung von Derivatives, LLM, Critic, XGBoost-Modell oder Delivery ist
nicht Teil dieser Messphase und braucht nach der Evidenz ein eigenes Review.

## 3. Start und Deployment-Gate

Für den isolierten Standalone-Nachweis (nur Test-Port) im Checkout:

```bash
PYTHON_BIN=python3 bash docs/r4/smoke-test.sh
```

Der Test wartet auf `/health`, prüft `/health`, `/signals/canonical/latest` und
`/metrics` als einen Vertrag und wiederholt die Prüfung nach einem TA-Zyklus.
Er validiert:

- `read_only`, gesunde/running Collector-Zustände und die TA-only Baseline;
- nicht ausführbare, dry-run-only Envelopes;
- Datenqualität, `created_at`, `freshness_seconds` und Invalidation-Alter;
- vollständige Monitoring-Metriken und einen nicht sinkenden
  `signals_stored_count`.

Im internen HermesTrader-Compose ohne freigegebenen Port den gleichen
Check innerhalb des Rainbow-Containers ausführen. Der Snapshot gehört in das
vorhandene Docker-Volume, nicht ins Git-Checkout:

```bash
docker compose exec -T rainbow python /app/scripts/r7_smoke_check.py \
  --base-url http://127.0.0.1:8000 \
  --expected-collector ta \
  --require-signal \
  --snapshot-path /app/rainbow/storage/r7-smoke-snapshot.json
```

Der Check erzeugt nur ein kleines JSON-Snapshot und lädt keine Python-Pakete
nach. Ein Fehler überschreibt den letzten erfolgreichen Snapshot nicht.

## 4. Tägliche Evidenz, 14 Tage lang

Täglich den Container-Check aus Abschnitt 3 ausführen und seinen JSON-Output
als Evidenz ablegen. Ergänze im R7-Tracking-Issue pro Tag:

1. Signale nach Quelle, Asset, Richtung und Timeframe; maximale Frische und
   stale/degraded/unavailable-Anzahl.
2. `signals_stored_count` gegenüber dem Vortag, Collector-Zyklen/Latenz und
   Fehlerzähler aus `/metrics/prometheus` bzw. Container-Logs.
3. Derivatives-Status (in dieser Baseline: deaktiviert), letzte Funding-Rate
   und API-Fehler, falls ein späterer, genehmigter Shadow-Test erfolgt.
4. `win_rate_rolling_50`, Calibration Error, Sample Size und Drift-Alarm;
   Outcome- und Backtest-Status.
5. Service-Uptime, `/health`-Fehler und ungeplante Neustarts.

Keine dieser Beobachtungen autorisiert eine automatische Aktivierung oder
Ausführung.

## 5. Release Gate und Rollback

Nach 14 vollständigen Tagen gelten die Kriterien in
[`R7-criteria.md`](R7-criteria.md). Das Go/No-Go entscheidet explizit über
eine **einzelne** nächste Erweiterung. Bei ungesundem Healthcheck, schlechter
Datenqualität, einem sinkenden Zähler oder einer Verletzung der Safety-Flags:

1. Delivery weiterhin `off` lassen.
2. Rainbow im Compose stoppen oder entfernen; der trading-hub behandelt die
   Quelle fail-closed als nicht verfügbar.
3. Evidenz und Logs am Tracking-Issue anfügen; erst dann Ursache beheben.
