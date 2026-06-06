# AI4Trade Bot -- Betriebs-Dokumentation

**Status:** Living Document
**Datum:** 2026-05-29
**Version:** 0.2.0
**Geltungsbereich:** Betrieb, Konfiguration, Monitoring, Troubleshooting

---

## 1. Start / Stop

### 1.1 Docker (empfohlen)

```bash
# Start
docker compose up -d

# Status pruefen
docker compose ps

# Logs anzeigen
docker compose logs -f ai4trade-bot

# Stop
docker compose down

# Neustart
docker compose restart
```

### 1.2 Lokale Ausfuehrung

**Voraussetzungen:**
- Python 3.11+
- `.env` Datei mit allen Pflicht-Variablen (siehe Abschnitt 2)

```bash
# Virtuelle Umgebung aktivieren
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Dependencies installieren
pip install -r requirements.txt

# Bot starten
python main.py
```

**Graceful Shutdown:** `Ctrl+C` (SIGINT) oder `kill <PID>` (SIGTERM). Bot beendet sauber mit Queue-Flush (5s Timeout).

### 1.3 Systemd (VPS)

```ini
# /etc/systemd/system/ai4trade-bot.service
[Unit]
Description=AI4Trade Bot
After=network.target

[Service]
Type=simple
User=hermes
WorkingDirectory=/home/hermes/projects/trading/ai4trade-bot
ExecStart=/home/hermes/projects/trading/ai4trade-bot/venv/bin/python main.py
Restart=on-failure
RestartSec=30
EnvironmentFile=/home/hermes/projects/trading/ai4trade-bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable ai4trade-bot
sudo systemctl start ai4trade-bot
sudo systemctl status ai4trade-bot
sudo systemctl stop ai4trade-bot
```

---

## 2. Konfiguration

Alle Konfiguration erfolgt ueber Umgebungsvariablen (`.env` Datei oder System-Environment).

### 2.1 Pflicht-Variablen

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `AI4TRADE_TOKEN` | JWT-Token fuer AI4Trade API | `eyJhbG...` |
| `CLAUDE_API_KEY` | Anthropic API Key fuer Sentiment | `sk-ant-...` |

### 2.2 Secret-Management

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `SECRET_BACKEND` | `env` | `env`, `keyring` oder `vault` |
| `VAULT_URL` | -- | HashiCorp Vault URL (nur bei `SECRET_BACKEND=vault`) |
| `VAULT_TOKEN` | -- | Vault Token (nur bei `SECRET_BACKEND=vault`) |

### 2.3 Signal-Konfiguration

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `ASSETS` | `BTC/USDT,ETH/USDT,SOL/USDT` | Liste der beobachteten Assets |
| `DATA_INTERVAL` | `60` | Marktdaten-Intervall in Sekunden |
| `SENTIMENT_INTERVAL` | `300` | Sentiment-Update in Sekunden |
| `HEARTBEAT_INTERVAL` | `30` | AI4Trade Heartbeat in Sekunden |
| `CONFIDENCE_THRESHOLD` | `60` | Minimaler Confidence-Schwellwert (0-100) |

### 2.4 Exchange-Konfiguration

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `EXCHANGE_PROVIDER` | `bitget` | Exchange-Provider (`bitget`) |
| `BITGET_BASE` | `https://api.bitget.com` | Bitget API Base URL |

### 2.5 LLM-Konfiguration

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `LLM_PROVIDER` | `claude` | `claude` oder `openai` |
| `CLAUDE_MODEL` | `claude-sonnet-4-5-20250929` | Claude Modell |
| `LLM_MODEL` | -- | Alternative Modellbezeichnung |
| `LLM_BASE_URL` | -- | Alternative API Base URL |
| `LLM_API_KEY` | -- | API Key fuer alternativen Provider |

### 2.6 Rate-Limiting

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `RATE_LIMIT_BITGET` | `10` | Max Requests/Sekunde Bitget |
| `RATE_LIMIT_COINGECKO` | `5` | Max Requests/Sekunde CoinGecko |
| `RATE_LIMIT_AI4TRADE` | `2` | Max Requests/Sekunde AI4Trade |
| `RATE_LIMIT_CRYPTOCOMPARE` | `5` | Max Requests/Sekunde CryptoCompare |
| `RATE_LIMIT_LLM` | `1` | Max Requests/Sekunde LLM API |

### 2.7 Persistenz

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `DB_PATH` | `storage/bot.db` | Pfad zur SQLite-Datenbank |
| `BACKUP_DIR` | `storage/backups` | Backup-Zielverzeichnis |
| `RETENTION_DAYS` | `7` | Backup-Aufbewahrung in Tagen |

### 2.8 Logging und Monitoring

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | `text` | `text` oder `json` |
| `MAX_SIGNAL_QUEUE` | `50` | Max gepufferte Signale |
| `METRICS_PORT` | `9090` | Prometheus-Metriken Port |

---

## 3. Monitoring

### 3.1 Prometheus

Prometheus scraped die Metriken vom Bot unter `http://localhost:9090/metrics`.

**Scrape-Konfiguration:**

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'ai4trade-bot'
    scrape_interval: 15s
    static_configs:
      - targets: ['ai4trade-bot:9090']
```

### 3.2 Verfuegbare Metriken

| Metrik | Typ | Labels | Beschreibung |
|--------|-----|--------|-------------|
| `bot_signals_total` | Counter | pair, action | Generierte Signale |
| `bot_signals_published_total` | Counter | pair, action | veroeffentlichte Signale |
| `bot_signals_blocked_total` | Counter | pair, reason | Blockierte Signale |
| `bot_api_latency_seconds` | Histogram | endpoint | API-Latenz |
| `bot_api_errors_total` | Counter | endpoint | API-Fehler |
| `bot_rate_limit_waits_total` | Counter | api | Rate-Limiter Wartezeiten |
| `bot_uptime_seconds` | Gauge | -- | Bot-Uptime |
| `bot_info` | Gauge | mode, version | Bot-Informationen |

### 3.3 Grafana Dashboard

Grafana-Verfuegbarkeit: `http://localhost:3000` (Default-Credentials: admin/admin)

**Empfohlene Panels:**
- Signal-Rate (Signals/min nach Pair und Action)
- API-Latenz P50/P95/P99
- Drawdown-Prozent ueber Zeit
- Offene Positionen
- Circuit Breaker Status
- Error-Rate nach Endpoint

### 3.4 Wichtige PromQL-Queries

```promql
# Signal-Rate (pro Minute)
rate(bot_signals_total[5m]) * 60

# Blockierte Signale pro Minute
rate(bot_signals_blocked_total[5m]) * 60

# API-Latenz P99
histogram_quantile(0.99, rate(bot_api_latency_seconds_bucket[5m]))

# Error-Rate
rate(bot_api_errors_total[5m]) / rate(bot_api_latency_seconds_count[5m])
```

---

## 4. Health-Check

### 4.1 HTTP Health-Endpoint

```bash
curl http://localhost:8080/health
```

**Erwartete Response:**

```json
{
  "status": "healthy",
  "uptime_seconds": 3600.5,
  "components": {
    "database": {"status": "healthy"},
    "exchange": {"status": "healthy"},
    "ai4trade_api": {"status": "healthy"}
  }
}
```

### 4.2 Manuelle Komponenten-Pruefung

```bash
# Bitget API Erreichbarkeit
curl -s https://api.bitget.com/api/v2/public/time

# SQLite Integritaet
sqlite3 storage/bot.db "PRAGMA integrity_check"

# Letzte Signale
sqlite3 storage/bot.db "SELECT * FROM signals ORDER BY created_at DESC LIMIT 5"

# Audit-Log
sqlite3 storage/bot.db "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 10"
```

---

## 5. Backup

### 5.1 Automatisches Backup (Cron-Job)

```cron
# Staendliches Backup
0 * * * * /app/scripts/backup.sh >> /app/storage/backups/backup.log 2>&1
```

### 5.2 Manuelles Backup

```bash
./scripts/backup.sh

# Mit eigenem Ziel
BACKUP_DIR=/mnt/backup/ai4trade ./scripts/backup.sh
```

### 5.3 Recovery

Siehe `docs/recovery.md` fuer die vollstaendige Recovery-Prozedur.

**Kurzfassung:**
1. Bot stoppen (`docker compose down`)
2. Aktuelle DB sichern (`cp storage/bot.db storage/bot.db.corrupted`)
3. Backup auswaehlen (`ls -lht storage/backups/bot_*.db`)
4. Backup wiederherstellen (`cp storage/backups/bot_YYYYMMDD_HHMMSS.db storage/bot.db`)
5. Bot starten (`docker compose up -d`)
6. Health-Check durchfuehren

---

## 6. Alerting

### 6.1 Aktive Alert-Regulen

| Alert | Bedingung | Severity | Bedeutung |
|-------|-----------|----------|-----------|
| `BotDown` | Keine Metriken fuer 2 Minuten | Critical | Bot-Prozess abgestuerzt |
| `CircuitBreakerActive` | `bot_circuit_breaker_active == 1` | Critical | Circuit Breaker ausgeloest |
| `HighErrorRate` | Error-Rate > 5% fuer 5 Minuten | Warning | API-Probleme |
| `HighLatency` | P99 > 5s fuer 5 Minuten | Warning | Performance-Probleme |
| `DrawdownWarning` | `bot_drawdown_pct > 15` | Warning | Nahe am Drawdown-Limit |
| `DrawdownCritical` | `bot_drawdown_pct > 20` | Critical | Drawdown-Limit erreicht |
| `BackupFailed` | Kein Backup in letzten 2 Stunden | Warning | Backup-Cron fehlerhaft |
| `StaleSignals` | Keine Signale fuer 10 Minuten | Warning | Trading-Loop blockiert |

### 6.2 AlertManager-Konfiguration

```yaml
# alertmanager.yml
route:
  receiver: 'default'
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 1h
receivers:
  - name: 'default'
    # Email, Slack, Webhook etc.
```

---

## 7. Troubleshooting

### 7.1 Bot startet nicht

| Symptom | Ursache | Loesung |
|---------|---------|---------|
| `AI4TRADE_TOKEN nicht gesetzt` | Fehlende `.env` | `.env` mit Token erstellen |
| `ASSETS nicht konfiguriert` | Fehlende Asset-Liste | `ASSETS=BTC/USDT,ETH/USDT` setzen |
| `ModuleNotFoundError` | Fehlende Dependencies | `pip install -r requirements.txt` |
| `Permission denied: storage/` | Fehlende Schreibrechte | `chmod 755 storage/` |

### 7.2 Keine Signale

| Symptom | Ursache | Loesung |
|---------|---------|---------|
| Alle Signale sind HOLD | Confidence unter Threshold | `CONFIDENCE_THRESHOLD` senken oder Strategy pruefen |
| Signale werden nicht gepublished | API-Fehler oder Queue-Problem | Logs prüfen, AI4Trade API-Verbindung testen |
| Publisher-Warteschlange voll | `MAX_SIGNAL_QUEUE` erreicht | `MAX_SIGNAL_QUEUE` erhöhen oder Queue leeren |

### 7.3 API-Probleme

| Symptom | Ursache | Loesung |
|---------|---------|---------|
| HTTP 429 (Bitget) | Rate-Limit überschritten | `RATE_LIMIT_BITGET` senken |
| HTTP 401 (AI4Trade) | Token abgelaufen | Token in `.env` erneuern |
| HTTP 5xx | Exchange downtime | Warten, Bot retryt automatisch |
| Timeout | Netzwerkprobleme | Netzwerk pruefen, `timeout` erhoehen |

### 7.4 Datenbank-Probleme

| Symptom | Ursache | Loesung |
|---------|---------|---------|
| `database is locked` | Parallel-Zugriff | Bot stoppen, DB pruefen, neustarten |
| `disk full` | Speicher voll | Alte Backups loeschen, `RETENTION_DAYS` pruefen |
| Korrupte DB | Hardware-Fehler | Recovery-Prozedur (`docs/recovery.md`) |

### 7.5 Sentiment immer neutral

| Symptom | Ursache | Loesung |
|---------|---------|---------|
| Score = 0.0 | API-Key fehlt | `CLAUDE_API_KEY` pruefen |
| Score = 0.0 | LLM-Fehler | `LOG_LEVEL=DEBUG` setzen, LLM-Response pruefen |
| Score = 0.0 | Keine News | CryptoCompare API pruefen |

### 7.6 MCP-Server Probleme

Siehe `docs/context/bitget-mcp-setup.md` Abschnitt 8 (Troubleshooting).

| Symptom | Loesung |
|---------|---------|
| MCP startet nicht | Node.js 18+ pruefen: `node --version` |
| Keine Daten | Bitget API pruefen: `curl https://api.bitget.com/api/v2/public/time` |
| HTTP 429 | Abfrage-Intervall erhoehen |

---

## 8. Verweise

| Dokument | Ort |
|----------|-----|
| Architektur | `docs/context/bitget-mcp-hybrid-architecture.md` |
| MCP Setup | `docs/context/bitget-mcp-setup.md` |
| Backup & Recovery | `docs/recovery.md` |
| Incident Response | `docs/incident-response.md` |
| GAP-Auditbericht | `docs/audit/GAP-Auditbericht-ai4trade-bot.md` |
| README | `README.md` |

---

## 9. Aenderungshistorie

| Datum | Aenderung |
|-------|-----------|
| 2026-05-29 | Initiale Erstellung |
