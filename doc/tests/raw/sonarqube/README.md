# Données brutes — SonarQube

Toutes les valeurs du document `06-analyse-statique.md` proviennent de ces
exports de l'API SonarQube (instance locale, 27/10/2026).

| Fichier | Passe | Contenu |
|---|---|---|
| `v1.0-summary.json` | v1.0 | synthèse calculée (métriques + répartitions) |
| `measures.json` | v1.0 | mesures (`/api/measures/component`) |
| `quality-gate.json` | v1.0 | *quality gate* |
| `issues.json` | v1.0 | 817 issues + facettes types/sévérités |
| `bugs.json` | v1.0 | 6 bugs |
| `vulnerabilities.json` | v1.0 | 285 vulnérabilités + facettes règles/fichiers |
| `measures-v1.1.json` | v1.1 | mesures intermédiaires (285 → 3) |
| `quality-gate-v1.1.json` | v1.1 | *quality gate* |
| `issues-v1.1.json` | v1.1 | 441 issues |
| `vulnerabilities-v1.1.json` | v1.1 | 3 vulnérabilités restantes |
| `measures-final.json` | v1.2 | mesures finales |
| `quality-gate-final.json` | v1.2 | *quality gate* finale (`Passed`) |
| `issues-final.json` | v1.2 | 438 issues finales |
| `bugs-final.json` | v1.2 | 6 bugs finaux |
| `issues-facets-final.json` | v1.2 | répartition par règle / sévérité |
| `dashboard.png` | v1.2 | capture du dashboard |
| `vulnerabilites.png` | v1.2 | capture des 2 findings Docker |
| `bugs.png` | v1.2 | capture des 6 bugs |

## Récupération

```bash
BASE=http://localhost:9000
TOKEN=<jeton admin>

curl -u "$TOKEN:" "$BASE/api/measures/component?component=somapro-backend\
&metricKeys=ncloc,bugs,vulnerabilities,code_smells,coverage,\
duplicated_lines_density,sqale_index,reliability_rating,security_rating,\
sqale_rating"

curl -u "$TOKEN:" "$BASE/api/qualitygates/project_status?\
projectKey=somapro-backend"

curl -u "$TOKEN:" "$BASE/api/issues/search?componentKeys=somapro-backend\
&resolved=false&ps=100&facets=types,severities,rules"
```

> Le jeton n'est **jamais** versionné (`/tmp/opencode/sonar_token.txt`).
> Pour le régénérer : `POST /api/user_tokens/generate` avec le compte admin.
