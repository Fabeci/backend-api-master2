#!/usr/bin/env bash
# Sauvegarde PostgreSQL + médias. Usage : ./backup.sh [/chemin/backups]
set -euo pipefail
BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE="$BACKEND/deploy/docker-compose.prod.yml"
ENVFILE="$BACKEND/deploy/.env.prod"
DEST="${1:-$BACKEND/backups}"
mkdir -p "$DEST"
STAMP="$(date +%Y%m%d_%H%M%S)"

set -a; . "$ENVFILE"; set +a
docker compose -f "$COMPOSE" --env-file "$ENVFILE" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$DEST/db_$STAMP.sql"
docker run --rm -v somapro_media:/media -v "$DEST":/backup alpine \
  tar czf "/backup/media_$STAMP.tar.gz" -C /media . 2>/dev/null || true
find "$DEST" -type f -mtime +14 -delete
echo "✅ Sauvegarde : $DEST (db_$STAMP.sql)"
