# AI4Trade Bot — Backup & Recovery

## Übersicht

| Kennzahl | Wert |
|----------|------|
| RPO (Recovery Point Objective) | 1 Stunde |
| RTO (Recovery Time Objective) | 4 Stunden |
| Backup-Methode | SQLite `.backup` (konsistente Kopie) |
| Aufbewahrung | 7 Tage (konfigurierbar) |
| Automatisierung | Cron-Job, stündlich |

Gesichert werden:
- SQLite-Datenbank (`storage/bot.db`) — Signale, Audit-Log, Konfiguration
- Bot-Logfile (`storage/bot.log`)

---

## Backup-Konfiguration

### Cron-Job (Linux/Docker)

```cron
# Stündliches Backup
0 * * * * /app/scripts/backup.sh >> /app/storage/backups/backup.log 2>&1
```

### Umgebungsvariablen

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `DB_PATH` | `storage/bot.db` | Pfad zur SQLite-Datenbank |
| `BACKUP_DIR` | `storage/backups` | Zielverzeichnis für Backups |
| `RETENTION_DAYS` | `7` | Aufbewahrungsfrist in Tagen |

### Docker (docker-compose.yml)

```yaml
environment:
  - DB_PATH=storage/bot.db
  - BACKUP_DIR=storage/backups
  - RETENTION_DAYS=7
volumes:
  - ./storage:/app/storage
```

---

## Manuelles Backup

```bash
# Standard-Backup
./scripts/backup.sh

# Backup mit eigenem Ziel
BACKUP_DIR=/mnt/backup/ai4trade ./scripts/backup.sh
```

---

## Recovery-Prozedur

### Schritt 1: Bot stoppen

```bash
# Docker
docker compose down

# Oder systemd
sudo systemctl stop ai4trade-bot
```

### Schritt 2: Aktuelle DB sichern (falls vorhanden)

Falls die Datenbank beschädigt, aber noch vorhanden ist — als Referenz aufheben:

```bash
cp storage/bot.db storage/bot.db.corrupted
```

### Schritt 3: Verfügbare Backups anzeigen

```bash
ls -lht storage/backups/bot_*.db
```

Das neueste Backup steht oben. Gewünschtes Backup anhand des Zeitstempels auswählen.

### Schritt 4: Backup wiederherstellen

```bash
# Zeitstempel des gewünschten Backups einsetzen
cp storage/backups/bot_YYYYMMDD_HHMMSS.db storage/bot.db
```

### Schritt 5: Bot neu starten

```bash
# Docker
docker compose up -d

# Oder systemd
sudo systemctl start ai4trade-bot
```

### Schritt 6: Health-Check durchführen

```bash
# Health-Endpoint aufrufen
curl http://localhost:8080/health
```

---

## Recovery-Validierung

Nach jeder Wiederherstellung MÜSSEN folgende Checks durchgeführt werden:

### 1. Health-Check

```bash
curl -s http://localhost:8080/health | python -m json.tool
```

Erwartet: Status `healthy` oder `ok`.

### 2. Letzte Signale prüfen

```bash
sqlite3 storage/bot.db "SELECT COUNT(*) FROM signals WHERE created_at > datetime('now', '-1 hour')"
```

Erwartet: Wert > 0 falls der Bot vor dem Backup-Zeitpunkt aktiv war.

### 3. Audit-Log prüfen

```bash
sqlite3 storage/bot.db "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 10"
```

Erwartet: Aktuelle Einträge, keine Fehlermeldungen bezüglich Datenintegrität.

### 4. Tabellen-Integrität prüfen

```bash
sqlite3 storage/bot.db "PRAGMA integrity_check"
```

Erwartet: `ok`.

---

## Disaster-Recovery

### Kompletter Datenbankverlust

Falls kein Backup verfügbar ist:

1. Bot startet automatisch mit leerer Datenbank — Tabellen werden beim Start erstellt
2. Alle historischen Signale und Audit-Einträge sind verloren
3. Der Bot generiert neue Signale basierend auf aktuellen Marktdaten
4. Konfiguration liegt in `config.py` und `.env` — nicht in der Datenbank

```bash
# Bot einfach neu starten — er erstellt die DB selbst
docker compose up -d
```

### Logfile-Wiederherstellung

Falls nur das Logfile benötigt wird:

```bash
# Neuestes Log-Backup suchen
ls -lht storage/backups/bot_*.log

# Wiederherstellen
cp storage/backups/bot_YYYYMMDD_HHMMSS.log storage/bot.log
```

---

## Monitoring

### Backup-Erfolg überwachen

```bash
# Prüfen ob heute ein Backup erstellt wurde
find storage/backups -name "bot_$(date +%Y%m%d)*.db" | wc -l
```

Erwartet: Wert >= 1.

### Backup-Größe überwachen

```bash
ls -lh storage/backups/bot_*.db | tail -5
```

Die Größe sollte konsistent sein. Plötzliche Größenänderungen deuten auf Probleme hin.

### Alerting

Der Cron-Job leitet Ausgabe nach `storage/backups/backup.log`. Bei Fehler:
- Script beendet mit Exit-Code 1
- Fehlermeldung wird geloggt
- Monitoring-System sollte auf Exit-Code != 0 reagieren
