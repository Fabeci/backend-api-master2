#!/usr/bin/env bash
# ============================================================================
# scripts/verify.sh — vérification complète de SOMAPRO (~2 min)
#   1. conteneurs   2. Django check   3. migrations   4. tests sécurité/LMD
#   5. build frontend                6. smoke API live (4 rôles)
# Usage : bash scripts/verify.sh
# ============================================================================
set -u
export PATH="$PATH:/mnt/c/Program Files/Docker/Docker/resources/bin"
# Racine du projet : soit le dossier parent (script à la racine), soit deux
# niveaux au-dessus (script dans <repo>/scripts/).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/docker-compose.yml" ] || ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1

DC="docker.exe compose"
API="http://localhost:8000/api/v1"
FAIL=0
ok()   { echo "  ✅ $1"; }
ko()   { echo "  ❌ $1"; FAIL=1; }
step() { echo; echo "── $1"; }

step "1. Conteneurs"
$DC ps --format "{{.Service}} {{.Status}}" 2>/dev/null | grep -E "backend|frontend|celery" || { ko "docker compose indisponible"; exit 1; }

step "2. Django check"
$DC exec -T backend python manage.py check 2>&1 | grep -q "no issues" && ok "check Django" || ko "check Django"

step "3. Migrations"
if $DC exec -T backend python manage.py migrate --check >/dev/null 2>&1; then
  ok "aucune migration en attente"
else
  ko "migrations en attente (python manage.py migrate)"
fi

step "4. Tests d'intégration (périmètres, publication, corrigés, LMD)"
if $DC exec -T backend python manage.py test core.tests_security core.tests_rbac -v1 2>&1 | grep -qE "^OK$"; then
  ok "tests backend"
else
  ko "tests backend"
fi

step "5. Frontend (build + réponse HTTP)"
$DC exec -T frontend true 2>/dev/null
if $DC logs --tail=40 frontend 2>&1 | grep -qiE "bundle generation failed|ERROR TS|ERROR NG"; then
  ko "erreurs de compilation frontend (voir logs)"
else
  ok "compilation frontend sans erreur"
fi
curl -s -o /dev/null -w "" --max-time 10 http://localhost:4200/ | grep -q . || true
[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://localhost:4200/)" = "200" ] \
  && ok "frontend 200" || ko "frontend indisponible"

step "6. Smoke API live"
_login_once() {
  curl -s --max-time 15 -X POST "$API/login/" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"password123\"}" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print((d.get('data') or {}).get('token') or '')" 2>/dev/null
}
login() {
  local t; t=$(_login_once "$1")
  if [ -z "$t" ]; then sleep 20; t=$(_login_once "$1"); fi
  echo "$t"
}
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$@"; }

A=$(login admin@testlms.com)
[ -n "$A" ] && ok "login admin" || ko "login admin (throttle ?)"
[ "$(code "$API/cours/" -H "Authorization: Token $A")" = "200" ] && ok "admin /cours/ 200" || ko "admin /cours/"
sleep 18
F=$(login formateur@testlms.com)
[ -n "$F" ] && ok "login formateur" || ko "login formateur"
[ "$(code "$API/cours/" -H "Authorization: Token $F")" = "200" ] && ok "formateur /cours/ 200" || ko "formateur /cours/"
sleep 18
R=$(login responsable@testlms.com)
[ -n "$R" ] && ok "login responsable" || ko "login responsable"
C=$(code -X POST "$API/sessions/" -H "Authorization: Token $R" -H 'Content-Type: application/json' \
      -d '{"formateur_id":342,"cours_id":37,"titre":"verify","date_debut":"2027-01-01T10:00:00Z","date_fin":"2027-01-01T12:00:00Z"}')
[ "$C" = "403" ] && ok "responsable : création de séance refusée (403)" || ko "responsable : séance = $C (403 attendu)"
sleep 18
P=$(login apprenant@testlms.com)
[ -n "$P" ] && ok "login apprenant" || ko "login apprenant"
[ "$(code "$API/cours/" -H "Authorization: Token $P")" = "200" ] && ok "apprenant /cours/ 200" || ko "apprenant /cours/"

echo
if [ "$FAIL" = "0" ]; then
  echo "✅ VÉRIFICATION RÉUSSIE"
else
  echo "❌ VÉRIFICATION EN ÉCHEC — corriger les points ci-dessus"
fi
exit "$FAIL"
