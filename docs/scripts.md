# Scripts-Übersicht

Dieses Dokument beschreibt die Utility-Scripts im `scripts/` Verzeichnis.

---

## `archive_signals.py`

**Zweck:** Monatlicher Signal-Archiv-Export für alte Signale (Issue #99)

**Beschreibung:** Exportiert Signale älter als N Tage als JSON-Archiv und löscht sie anschließend aus der Hot-Tier SQLite-Datenbank. Gedacht als Cron-Job am 1. jedes Monats um 03:00 UTC.

**Verwendung:**
```bash
# Signale älter als 30 Tage archivieren
python scripts/archive_signals.py --days 30

# Dry-Run (nur anzeigen, nicht löschen)
python scripts/archive_signals.py --dry-run --output-dir /tmp/archive
```

**Konfiguration:**
- `--days`: Alter-Schwellenwert in Tagen (Default: 30)
- `--dry-run`: Nur Vorschau, keine Löschung
- `--output-dir`: Zielverzeichnis für JSON-Archive (Default: `data/archive`)

**Abhängigkeiten:**
- Benötigt `CanonicalSignalRegistry` (SQLite-Datenbank)
- Liest aus `DB_PATH` Environment-Variable

---

## `backup.sh`

**Zweck:** SQLite-Backup-Script für `bot.db` mit Retention-Management

**Beschreibung:** Erstellt sichere SQLite-Backups (verhindert Corruption bei concurrenten Writes) und räumt alte Backups nach Retention-Policy auf.

**Verwendung:**
```bash
# Standard-Backup
./scripts/backup.sh

# Mit Custom-Parametern
DB_PATH=storage/bot.db BACKUP_DIR=storage/backups RETENTION_DAYS=7 ./scripts/backup.sh
```

**Environment-Variables:**
- `DB_PATH`: Pfad zur SQLite-Datenbank (Default: `storage/bot.db`)
- `BACKUP_DIR`: Backup-Verzeichnis (Default: `storage/backups`)
- `RETENTION_DAYS`: Aufbewahrungsdauer in Tagen (Default: 7)

**Output:**
- Backup: `storage/backups/bot_YYYYMMDD_HHMMSS.db`
- Log-Backup: `storage/backups/bot_YYYYMMDD_HHMMSS.log` (falls `storage/bot.log` existiert)

---

## `check_rainbow_metadata_completeness.py`

**Zweck:** Fixture-basierte Validierung der Rainbow-Signal-Metadaten (Issue #58)

**Beschreibung:** Prüft Rainbow-Signal-Fixtures auf vollständige Metadaten-Struktur. Validiert Required/Optional Top-Level-Felder und Metadata-Keys.

**Verwendung:**
```bash
# Alle Fixtures prüfen
python scripts/check_rainbow_metadata_completeness.py

# Einzelne Fixture prüfen
python scripts/check_rainbow_metadata_completeness.py --fixture docs/integration/fixtures/rainbow-signals/signal-001.json
```

**Validiert:**
- **Required Top-Level:** `event_type`, `schema_version`, `source_system`, `source_id`, `strategy_id`, `symbol`, `timestamp_utc`, `direction`, `confidence`, `metadata`, `redaction_status`
- **Optional Top-Level:** `model_id`, `timeframe`, `emitted_at_utc`, `signal_strength`, `regime_hint`
- **Optional Metadata-Keys:** `reason_codes`, `data_quality`, `features`, `raw_refs`

**Exit-Codes:**
- `0` — Alle Fixtures vollständig
- `1` — Fehlende/ungültige Metadaten gefunden

---

## `generate_audit_artifacts.py`

**Zweck:** Generierung von PDF- und PPTX-Artefakten aus Markdown-Audit-Reports

**Beschreibung:** Konvertiert Markdown-Audit-Reports und Slide-Outlines in strukturierte PDF-Berichte und PowerPoint-Präsentationen.

**Verwendung:**
```bash
python scripts/generate_audit_artifacts.py
```

**Input:**
- `docs/audit/2026-05-29-ai4trade-bot-audit-report.md`
- `docs/audit/2026-05-29-ai4trade-bot-slide-outline.md`

**Output:**
- `docs/audit/AI4Trade-Bot-Auditbericht-2026-05-29.pdf`
- `docs/audit/AI4Trade-Bot-Executive-Briefing-2026-05-29.pptx`

**Abhängigkeiten:**
- `reportlab` (PDF-Generierung)
- `python-pptx` (PowerPoint-Generierung)

---

## `r7_smoke_check.py`

**Zweck:** Read-only Deployment-Gate für die 14-tägige Rainbow R7 Shadow-Phase

**Beschreibung:** Minimalistische Smoke-Check-Validierung für Rainbow-Deployments. Verwendet nur Python Standard Library. Prüft Rainbow-HTTP-Endpunkte ohne Dependencies.

**Verwendung:**
```bash
# Standard-Check gegen http://localhost:8000
python scripts/r7_smoke_check.py

# Custom Base-URL
python scripts/r7_smoke_check.py --base-url http://rainbow.example.com:8000

# Snapshot speichern
python scripts/r7_smoke_check.py --snapshot-path /tmp/rainbow-snapshot.json
```

**Prüfungen:**
- `/health` — System-Status
- `/signals/latest` — Signal-Retrieval
- `/metrics` — Metriken-Endpoint

**Exit-Codes:**
- `0` — Alle Checks OK
- `1` — Fehler gefunden (siehe JSON-Output)

---

## `train_xgboost.py`

**Zweck:** XGBoost-Modell-Training für die `PredictiveEngine`

**Beschreibung:** Trainiert ein XGBoost-Klassifikationsmodell auf OHLCV-Daten. Baut Features via `core.feature_pipeline.FeaturePipeline`, erstellt binäre Labels (Preis steigt/fällt nächste Periode) und speichert das trainierte Modell.

**Verwendung:**
```bash
# Training mit CSV-Daten
python scripts/train_xgboost.py --data path/to/ohlcv.csv --output models/predictive/

# Mit Custom Test-Split
python scripts/train_xgboost.py --data path/to/ohlcv.csv --output models/predictive/ --test-size 0.2
```

**Input-Schema (CSV):**
- **Required:** `open`, `high`, `low`, `close`, `volume`
- **Optional:** `timestamp` (datetime) oder DataFrame-Index

**Output:**
- `models/predictive/xgboost_v1.json` — Trainiertes XGBoost-Modell

**Abhängigkeiten:**
- `xgboost`
- `pandas`, `numpy`
- `core.feature_pipeline.FeaturePipeline`

---

## `validate_config.py`

**Zweck:** Validierung der Hermes-Orchestrator-Config auf Mindestanforderungen

**Beschreibung:** Prüft ob die Orchestrator-Config (YAML) die Mindest-Config-Version erfüllt (aktuell: v28).

**Verwendung:**
```bash
python scripts/validate_config.py
```

**Config-Suchpfade (in Reihenfolge):**
1. `config.yaml`
2. `config.yml`
3. `.hermes/config.yaml`
4. `../config.yaml`

**Validiert:**
- `config_version >= 28` (aktuelles Minimum)

**Exit-Codes:**
- `0` — Config OK
- `1` — Config fehlt oder zu alt

---

## Weitere Hinweise

**Backup-Strategie:** `backup.sh` sollte als Cron-Job laufen (z.B. täglich um 02:00 UTC):
```cron
0 2 * * * /app/scripts/backup.sh >> /var/log/backup.log 2>&1
```

**Archivierungs-Strategie:** `archive_signals.py` sollte monatlich laufen (z.B. 1. des Monats um 03:00 UTC):
```cron
0 3 1 * * /app/.venv/bin/python /app/scripts/archive_signals.py --days 30 >> /var/log/archive.log 2>&1
```

**XGBoost-Training:** Benötigt historische OHLCV-Daten. Für Produktions-Training: Daten aus Bitget/CoinGecko via Rainbow Market-Data-Module abrufen und als CSV exportieren.
