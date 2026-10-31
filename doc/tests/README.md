# Dossier de tests — SOMAPRO

Ce dossier regroupe la **stratégie**, le **cahier de tests**, le **rapport
d'exécution**, le **rapport de performance** et la **matrice de traçabilité**
de la plateforme SOMAPRO (LMS).

> ⚠️ Tous les chiffres proviennent d'exécutions réelles (voir `raw/`).
> Les éléments **non exécutés** sont explicitement signalés.

## Sommaire

| Fichier | Contenu |
|---|---|
| `01-strategie.md` | Périmètre, architecture testée, outils, environnements, risques, limites |
| `02-cahier-de-tests.md` | Cas de test, préconditions, résultats attendus/observés, statuts |
| `03-rapport-execution.md` | Résultats réels, couverture, anomalies, corrections |
| `04-rapport-performance.md` | Charge réelle, latences, débit, analyse |
| `05-matrice-tracabilite.md` | Exigences → tests → statut |
| `06-analyse-statique.md` | Analyse SonarQube (3 passes, avant/après, triage) |
| `07-tests-securite.md` | Tests d'attaques : SQLi, XSS, IDOR, mass assignment, auth, upload, CORS, dépendances |
| `raw/` | Sorties brutes (coverage, perf, sécurité, Karma, SonarQube) |

## Commandes de reproduction

### Backend — suite complète (201 tests)

```bash
docker compose run --rm --no-deps backend \
  python manage.py test core courses evaluations users academics analytics \
    progress notifications resources collaborations feedback gamification locations parametres
```

### Backend — couverture

```bash
docker compose run --rm --no-deps backend sh -c "
  pip install -q coverage &&
  coverage run --source=core,courses,evaluations,users,academics,analytics,progress,notifications,resources,collaborations,feedback,gamification,locations,parametres \
    manage.py test core courses evaluations users academics analytics progress notifications resources collaborations feedback gamification locations parametres &&
  coverage report --omit='*/migrations/*,*/tests*.py,*/env/*' -m
"
```

### Frontend — suite critique (33 tests)

```bash
# Chromium requis dans le conteneur : apt-get install -y chromium
docker compose exec -e CHROME_BIN=/usr/bin/chromium frontend \
  npx ng test --watch=false --browsers=ChromeHeadlessNoSandbox \
  --ts-config=tsconfig.spec.critical.json \
  --include='src/app/services/cours/chat-tuteur/**/*.spec.ts' \
  --include='src/app/components/courses/cours/cours-detail/course-player/chat-tuteur/**/*.spec.ts' \
  --include='src/app/services/notifications/**/*.spec.ts' \
  --include='src/app/interceptors/offline-cache.interceptor.spec.ts'
```

### Sécurité

```bash
python manage.py test core.tests_attaques \
  --settings=master_backend_api.test_settings -v2

bash scripts/tests/security_checks.sh
```

### Analyse statique (SonarQube, local)

```bash
docker compose -f docker-compose.sonar.yml up -d        # attendre status = UP
coverage xml -o coverage.xml                            # suite exécutée avant
docker run --rm --add-host=host.docker.internal:host-gateway \
  -v "$PWD:/usr/src" -w /usr/src -e SONAR_TOKEN="$TOKEN" \
  sonarsource/sonar-scanner-cli \
  -Dsonar.host.url=http://host.docker.internal:9000
```

Détail des trois passes et des arbitrages : `06-analyse-statique.md`.

### Performance (local, serveur de dev)

```bash
python3 scripts/tests/perf_api.py --duration 20 --concurrency 5
python3 scripts/tests/perf_api.py --duration 20 --concurrency 10
```

## Résumé

| Catégorie | Résultat réel |
|---|---|
| Tests backend | **201 / 201 réussis** (176 s) |
| Tests frontend critiques | **33 / 33 réussis** |
| Couverture backend (code applicatif) | **40 %** global ; **69–98 %** sur les modules critiques |
| Sécurité (tests d'attaque) | **19 / 19 réussis** — voir `07-tests-securite.md` |
| Audit dépendances | **35 vulnérabilités npm**, **198 avis pip** — plan de montée de version à prévoir |
| Analyse statique (SonarQube) | **2 vulnérabilités** (Docker de dev) · **0 blocker** · *quality gate* **Passed** · couverture **39,4 %** |
| Charge locale (5 utilisateurs) | 32,2 req/s · p95 297 ms · **0 erreur** |
| Charge locale (10 utilisateurs) | 32,1 req/s · p95 531 ms · **0 erreur** |
| E2E navigateur (Playwright/Selenium) | **non exécuté** (outil absent) |
| Qualité IA avec fournisseur cloud réel | **à réaliser** (aucune clé en production) |
