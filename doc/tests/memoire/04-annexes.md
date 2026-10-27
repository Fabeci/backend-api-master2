# Annexes à joindre au mémoire

> Les annexes ne doivent pas contenir de secrets (mots de passe, clés API,
> tokens). Les identifiants de démonstration doivent être fictifs.

## Annexe A — Cahier de tests
Fichier : `doc/tests/02-cahier-de-tests.md`
Contenu : identifiants, préconditions, attendus, observés, statuts
(unitaires, intégration, frontend, sécurité, performance, IA).

## Annexe B — Rapport d'exécution
Fichier : `doc/tests/03-rapport-execution.md`
Contenu : volumes, résultats, couverture, anomalies, corrections, limites.

## Annexe C — Couverture détaillée
Fichiers : `doc/tests/raw/coverage-app.txt`, `raw/coverage-app-v2.txt`
Contenu : rapport `coverage.py` module par module (lignes, manquantes, %).
Conseil : joindre les 2 premières pages (totaux + modules applicatifs), pas les
migrations.

## Annexe D — Performance
Fichiers : `doc/tests/04-rapport-performance.md`, `raw/perf-concurrency5.json`,
`raw/perf-concurrency10.json`
Contenu : environnement, paramètres, latences (moyenne, p50/p95/p99), débit,
taux d'erreur, analyse du goulot.

## Annexe E — Sécurité
Fichiers : `doc/tests/raw/security-checks.txt`,
`scripts/tests/security_checks.sh`
Contenu : 7 contrôles (menace → attendu → observé) et script reproductible.
**Ne pas joindre** de captures contenant des identifiants réels.

## Annexe F — Matrice de traçabilité
Fichier : `doc/tests/05-matrice-tracabilite.md`
Contenu : exigences E1→E25 → tests → statut.

## Annexe G — Extraits de code de test
Fichiers :
- `core/tests_metier.py` (50 tests unitaires)
- `courses/tests_chat.py` (43 tests chat/IA)
- `core/tests_security.py`, `core/tests_rbac.py`
- `evaluations/tests_explication.py`
- `scripts/tests/perf_api.py`, `scripts/tests/security_checks.sh`
- frontend : `karma.conf.js`, `tsconfig.spec.critical.json`

Conseil : joindre 2 à 4 extraits représentatifs (test de valeur limite,
test d'isolation, test de refus d'injection, test de déblocage) plutôt que
l'intégralité des fichiers.

## Annexe H — Preuves d'exécution continue
Captures ou exports :
- run GitHub Actions **CI backend** (tests + couverture + artefact) ;
- run **CI frontend** (build + 33 tests) ;
- runs **Deploy backend/frontend** (succès).
Les identifiants de run sont dans `doc/tests/03-rapport-execution.md` (§3.7).

## Mise en forme des annexes
- Numérotation **A, B, C…** et pagination continue.
- En-tête « Annexe X — titre ».
- Extraits de code en police monospace, avec **légende** (fichier + rôle).
- Tableaux avec titres (`Tableau A.1`, `Tableau B.1`, …).
- Référencer chaque annexe dans le corps : « (voir annexe B) ».
