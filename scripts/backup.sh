#!/usr/bin/env bash
# AI4Trade Bot SQLite Backup
set -euo pipefail

DB_PATH="${DB_PATH:-storage/bot.db}"
BACKUP_DIR="${BACKUP_DIR:-storage/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Backup-Verzeichnis erstellen
mkdir -p "$BACKUP_DIR"

# SQLite sichere Kopie (verhindert Corruption bei concurrenten Writes)
if [ -f "$DB_PATH" ]; then
    sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/bot_${TIMESTAMP}.db'"
    echo "[$(date)] Backup erstellt: $BACKUP_DIR/bot_${TIMESTAMP}.db"
else
    echo "[$(date)] WARNUNG: $DB_PATH nicht gefunden"
    exit 1
fi

# Logs sichern
if [ -f "storage/bot.log" ]; then
    cp "storage/bot.log" "$BACKUP_DIR/bot_${TIMESTAMP}.log"
fi

# Alte Backups aufräumen (Retention)
find "$BACKUP_DIR" -name "bot_*.db" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "bot_*.log" -mtime +$RETENTION_DAYS -delete
echo "[$(date)] Backups älter als $RETENTION_DAYS Tage aufgeräumt"

# Backup-Größe anzeigen
SIZE=$(du -sh "$BACKUP_DIR/bot_${TIMESTAMP}.db" | cut -f1)
echo "[$(date)] Backup-Größe: $SIZE"
