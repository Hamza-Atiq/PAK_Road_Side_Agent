#!/usr/bin/env bash
# ============================================================
# RoadSide Agent — PostgreSQL backup
# - Runs pg_dump inside the running postgres container.
# - Optionally uploads to S3 if BACKUP_S3_BUCKET is set + aws cli present.
# - Otherwise just keeps a rolling local archive (BACKUP_KEEP rotations).
#
# Cron (daily at 02:30):
#   30 2 * * *  /srv/roadside/infrastructure/scripts/backup-postgres.sh \
#               >> /var/log/roadside/backup.log 2>&1
# ============================================================
set -euo pipefail

CONTAINER="${POSTGRES_CONTAINER:-roadside-postgres}"
DB_USER="${POSTGRES_USER:-roadside}"
DB_NAME="${POSTGRES_DB:-roadside}"
BACKUP_DIR="${BACKUP_DIR:-/srv/roadside/backups}"
BACKUP_KEEP="${BACKUP_KEEP:-14}"          # days of local backups to keep
S3_BUCKET="${BACKUP_S3_BUCKET:-}"          # optional
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/${DB_NAME}-${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] backup start: $OUT"
docker exec "$CONTAINER" \
  pg_dump --no-owner --no-acl --format=plain --create -U "$DB_USER" "$DB_NAME" \
  | gzip --best > "$OUT"

SIZE=$(du -h "$OUT" | cut -f1)
echo "[$(date -Iseconds)] backup written ($SIZE)"

# Optional S3 upload
if [[ -n "$S3_BUCKET" ]]; then
  if command -v aws >/dev/null 2>&1; then
    aws s3 cp "$OUT" "s3://$S3_BUCKET/postgres/$(basename "$OUT")" --only-show-errors
    echo "[$(date -Iseconds)] uploaded to s3://$S3_BUCKET/postgres/"
  else
    echo "[$(date -Iseconds)] WARN: BACKUP_S3_BUCKET set but aws CLI missing; skipping upload"
  fi
fi

# Local rotation: delete anything older than BACKUP_KEEP days.
find "$BACKUP_DIR" -name "${DB_NAME}-*.sql.gz" -mtime "+$BACKUP_KEEP" -delete
echo "[$(date -Iseconds)] rotation done (kept last $BACKUP_KEEP days)"
