#!/usr/bin/env bash
# ============================================================================
# Déploiement backend sur cPanel (Passenger), sans Docker.
#
# Peut être lancé :
#   - depuis le Terminal cPanel ;
#   - depuis une tâche cron ponctuelle ;
#   - depuis le bouton « Pull or Deploy » de Git Version Control (.cpanel.yml).
#
# Variables d'environnement optionnelles :
#   VENV       chemin du virtualenv (défaut : $HOME/virtualenv/somaproapi/3.12)
#   REQ_FILE   fichier de dépendances (défaut : requirements.cpanel.txt)
#   SKIP_PULL  1 = ne pas faire « git pull »
# ============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$APP_DIR"

VENV="${VENV:-$HOME/virtualenv/somaproapi/3.12}"
REQ_FILE="${REQ_FILE:-requirements.cpanel.txt}"

echo "── 1. Code ($APP_DIR)"
if [ "${SKIP_PULL:-0}" = "1" ]; then
  echo "   (git pull ignoré)"
else
  git pull --ff-only || echo "⚠️  git pull impossible — on continue avec le code présent"
fi

echo "── 2. Environnement"
if [ ! -f .env ]; then
  echo "❌ .env absent : copier .env.example vers .env et renseigner DJANGO_SECRET_KEY"
  exit 1
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "── 3. Dépendances ($REQ_FILE)"
pip install --upgrade pip >/dev/null
pip install -r "$REQ_FILE"

echo "── 4. Base de données"
python manage.py migrate --noinput

echo "── 5. Fichiers statiques"
python manage.py collectstatic --noinput >/dev/null

echo "── 6. Redémarrage Passenger"
mkdir -p tmp
touch tmp/restart.txt

echo "── 7. Contrôle"
python manage.py check

echo "✅ Backend cPanel déployé"
