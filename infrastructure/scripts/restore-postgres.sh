#!/usr/bin/env bash
# ============================================================
# Restore a pg_dump archive into the running postgres container.
# WARNING: destructive — drops the target DB before restore. Run with
# the API + Celery containers stopped to avoid in-flight writes.
# ============================================================
set -euo pipefail

ARCHIVE="${1:?Usage: restore-postgres.sh <path-to-dump.sql.gz>}"
CONTAINER="${POSTGRES_CONTAINER:-roadside-postgres}"
DB_USER="${POSTGRES_USER:-roadside}"
DB_NAME="${POSTGRES_DB:-roadside}"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "ERROR: archive not found: $ARCHIVE" >&2
  exit 1
fi

read -r -p "This will DROP and restore $DB_NAME from $ARCHIVE. Continue? [y/N] " ans
[[ "$ans" =~ ^[Yy]$ ]] || { echo "aborted"; exit 1; }

echo "==> dropping & recreating $DB_NAME"
docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$DB_NAME\";"
docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -c "CREATE DATABASE \"$DB_NAME\";"

echo "==> restoring $ARCHIVE"
gunzip -c "$ARCHIVE" | docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME"

echo "==> ensuring required extensions"
docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
  "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS pgcrypto;"

echo "==> done"
