#!/usr/bin/env bash
# Munshi AI - Automated Daily Postgres Backup & Retention Policy
set -Eeuo pipefail

BACKUP_DIR="/src/storage/backups"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/postgres_backup_${TIMESTAMP}.dump"
LOG_FILE="${BACKUP_DIR}/backup_log.txt"

mkdir -p "${BACKUP_DIR}"

echo "[$(date)] Starting daily Postgres backup..." | tee -a "${LOG_FILE}"

# Trigger a custom-format PostgreSQL backup using environment variables
if PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_dump -h "${DB_HOST:-postgres}" -U "${POSTGRES_USER:-erp_admin}" -d "${POSTGRES_DB:-ai_erp}" -F c -f "${BACKUP_FILE}"; then
  echo "[$(date)] Backup completed successfully: ${BACKUP_FILE}" | tee -a "${LOG_FILE}"
  
  # Retention pruning - delete backups older than RETENTION_DAYS
  echo "[$(date)] Pruning old backups exceeding ${RETENTION_DAYS}-day threshold..." | tee -a "${LOG_FILE}"
  find "${BACKUP_DIR}" -name "postgres_backup_*.dump" -type f -mtime +"${RETENTION_DAYS}" -exec rm -f {} \; -print | tee -a "${LOG_FILE}"
  echo "[$(date)] Backup maintenance complete." | tee -a "${LOG_FILE}"
else
  echo "[$(date)] ERROR: Backup execution failed!" | tee -a "${LOG_FILE}" >&2
  exit 1
fi
