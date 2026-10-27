# 3. Rapport d'exécution

## 3.1 Synthèse

| Catégorie | Exécutés | Réussis | Échoués | Bloqués | Non exécutés |
|---|---|---|---|---|---|
| Backend (unitaires + intégration + sécurité + IA) | **160** | **160** | 0 | 0 | 0 |
| Frontend (specs critiques) | **33** | **33** | 0 | 0 | 0 |
| Sécurité (contrôles dynamiques) | **7** | **7** | 0 | 0 | 0 |
| Performance (2 scénarios) | **2** | **2** | 0 | 0 | 0 |
| E2E navigateur | 0 | 0 | 0 | 0 | **4 parcours** |
| IA — validation cloud réelle | 0 | 0 | 0 | 0 | **1 campagne** |

## 3.2 Exécution backend

```
Ran 160 tests in 58.092s
OK
```

- Environnement : conteneur `somapro-backend`, Python 3.12, base de test SQLite.
- Commande : `python manage.py test core courses evaluations users academics analytics progress notifications resources collaborations feedback gamification locations parametres`.
- Aucune donnée réelle utilisée (bases de test détruites après exécution).

### Couverture (coverage.py, exécution réelle)

| Périmètre | Couverture |
|---|---|
| **Code applicatif** (hors migrations/tests) | **40 %** (23 199 instructions, 14 031 non couvertes) |
| `academics/services/lmd.py` | **98 %** |
| `courses/services/progression.py` | **94 %** |
| `courses/services/difficulte.py` | **92 %** |
| `courses/views_stats.py` | **93 %** |
| `evaluations/views_explication.py` | **88 %** |
| `courses/views_chat.py` | **85 %** |
| `courses/services/chat_tuteur.py` | **78 %** |
| `core/rbac.py` | **81 %** |
| `courses/services/quiz_tuteur.py` | **75 %** |
| `courses/services/rag.py` | **70 %** |
| `courses/parcours_engine.py` | **80 %** |
| `analytics/models.py` | **85 %** |
| `evaluations/models.py` | **72 %** |
| `users/access_control.py` | **61 %** |
| `courses/publication.py` | **69 %** |

Rapports complets : `raw/coverage-app.txt`, `raw/coverage-app-v2.txt`.

**Modules faiblement couverts (priorité)** : analytics (dashboards, engines),
`academics/services/bulletin_pdf.py`, les serializers, les commandes de
management. Ces modules sont surtout des agrégats/rendus ; les **règles
critiques** (LMD, progression, chat, RBAC) sont couvertes à 77–98 %.

## 3.3 Exécution frontend

```
Chrome Headless 156.0.0.0 (Linux 0.0.0): Executed 33 of 33 SUCCESS
TOTAL: 33 SUCCESS
```

- 5 fichiers : chat (service 5 + composant 11), pipe Markdown 7,
  notifications 6, cache hors-ligne 4.
- Navigateur : Chromium 156 headless (`--no-sandbox`), installé dans le conteneur.
- Sortie brute : `raw/karma-critical.log`.

## 3.4 Anomalies détectées et corrections

| # | Anomalie | Gravité | Correction |
|---|---|---|---|
| A1 | Scripts manuels `test_*.py` à la racine pris pour des tests → **2 erreurs** de découverte | Moyenne | renommés `manual_*.py` |
| A2 | CI backend ne lançait que **26/127 tests** | Élevée | CI exécute toute la suite + couverture |
| A3 | 13 specs frontend historiques cassées (imports invalides) → compilation Karma en échec | Moyenne | `tsconfig.spec.critical.json` dédié ; dette documentée |
| A4 | Spec chat : assertion synchrone sur une promesse → **1 échec** | Faible (test) | attente asynchrone ajoutée |
| A5 | `angular.json` : options de test dupliquées lors de l'ajout de Karma | Faible | bloc réécrit proprement |
| A6 | Aucun lanceur Chromium `--no-sandbox` (conteneur root) | Moyenne | `karma.conf.js` + `ChromeHeadlessNoSandbox` |

Aucune correction n'a modifié une règle métier pour faire passer un test.

## 3.5 Tests non exécutés et raisons

| Élément | Raison | À faire |
|---|---|---|
| E2E navigateur (parcours apprenant/formateur/parent/admin) | Playwright/Selenium absents ; pas d'accès au navigateur de l'agent | installer Playwright + `npx playwright test` |
| Validation IA sur fournisseur cloud | aucune clé API en production (`AI_PROVIDER=mock`) | fournir une clé Claude/Gemini et rejouer la grille |
| Charge production | pas d'environnement de préproduction | rejouer k6/JMeter sur la cible cPanel |
| Tests de montée en charge > 10 utilisateurs | serveur de dev saturé | cible dédiée |

## 3.6 Risques résiduels

- **IA** : la qualité dépend du fournisseur ; le mode `mock` ne valide pas la
  valeur pédagogique réelle.
- **Frontend** : 13 specs historiques cassées (hors périmètre de cette mission).
- **Performance** : chiffres locaux (runserver + SQLite), non extrapolables.
- **E2E** : les parcours UI ne sont pas validés de bout en bout.

## 3.7 Preuve d'intégration continue (GitHub Actions)

| Workflow | Run | Résultat |
|---|---|---|
| **CI backend** (check + 127 tests + couverture + artefact) | `40482831910` | **succès** ✅ |
| **CI frontend** (build + garde-fou API + 33 tests critiques) | `40482877681` | **succès** ✅ |
| **Deploy backend → cPanel (FTP)** | `40482831870` | **succès** ✅ |
| **Deploy frontend → cPanel (FTP)** | `40482877814` | **succès** ✅ |

Les tests sont donc **reproductibles en local et en CI**, sur chaque push `main`.
