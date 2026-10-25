#!/usr/bin/env bash
# ============================================================================
# Déploiement serveur (LWS VPS). Appelé par GitHub Actions ou à la main.
# Layout attendu : /opt/somapro/{backend-api-master2,master-frontend}
# ============================================================================
set -euo pipefail

BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$BACKEND/.." && pwd)"
FRONTEND="$ROOT/master-frontend"
COMPOSE="$BACKEND/deploy/docker-compose.prod.yml"
ENVFILE="$BACKEND/deploy/.env.prod"

echo "── 1. Mise à jour du code"
git -C "$BACKEND" pull --ff-only
[ -d "$FRONTEND/.git" ] && git -C "$FRONTEND" pull --ff-only

echo "── 2. Vérification de la configuration"
[ -f "$ENVFILE" ] || { echo "❌ $ENVFILE manquant"; exit 1; }

echo "── 3. Build + démarrage"
docker compose -f "$COMPOSE" --env-file "$ENVFILE" up -d --build

echo "── 4. Migrations + statiques"
docker compose -f "$COMPOSE" --env-file "$ENVFILE" exec -T backend python manage.py migrate --noinput
docker compose -f "$COMPOSE" --env-file "$ENVFILE" exec -T backend python manage.py collectstatic --noinput

echo "── 5. Vérification"
docker compose -f "$COMPOSE" --env-file "$ENVFILE" ps
docker compose -f "$COMPOSE" --env-file "$ENVFILE" exec -T backend python manage.py check

echo "✅ Déploiement terminé"
