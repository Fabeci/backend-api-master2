#!/usr/bin/env bash
# ============================================================================
# Remplace Celery Beat sur cPanel (pas de worker persistant).
# À planifier toutes les 5 minutes via « Cron Jobs » cPanel :
#   */5 * * * * /bin/bash /home/USER/somapro/backend-api-master2/deploy/cpanel/cron_publication.sh
# ============================================================================
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$APP_DIR"
VENV="${VENV:-$HOME/virtualenv/somaproapi/3.12}"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

python manage.py shell -c "
from master_backend_api.tasks import publier_contenus_programmes, rappels_sessions_a_venir
publier_contenus_programmes()
rappels_sessions_a_venir()
"
