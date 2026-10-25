#!/usr/bin/env bash
# ============================================================================
# Déploiement backend sur cPanel (SSH), sans Docker.
# Prérequis : dépôt cloné, virtualenv créé via « Setup Python App »,
#             fichier .env à la racine (voir .env.prod.example).
# ============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$APP_DIR"

# Virtualenv cPanel (adapter la version de Python si besoin)
VENV="${VENV:-$HOME/virtualenv/somaproapi/3.12}"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "── 1. Code"
git pull --ff-only

echo "── 2. Dépendances"
pip install --upgrade pip >/dev/null
pip install -r requirements.docker.txt

echo "── 3. Base de données"
python manage.py migrate --noinput

echo "── 4. Fichiers statiques"
python manage.py collectstatic --noinput

echo "── 5. Redémarrage Passenger"
mkdir -p tmp
touch tmp/restart.txt

echo "── 6. Contrôle"
python manage.py check

echo "✅ Backend cPanel déployé"
