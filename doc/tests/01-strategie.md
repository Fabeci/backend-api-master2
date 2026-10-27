# 1. Stratégie de test

## 1.1 Objectifs

Valider la plateforme SOMAPRO sur cinq axes :
1. **Fonctionnel** : règles métier (progression, LMD, publication, quiz).
2. **Sécurité** : authentification, autorisations, isolation des données, IA.
3. **Non-régression** : suite reproductible à chaque évolution.
4. **Performance** : latence/débit des endpoints critiques.
5. **Qualité IA** : comportement du tuteur (contexte, refus, erreurs).

## 1.2 Architecture testée

| Couche | Technologie | Testée par |
|---|---|---|
| API | Django 5.1.6 + DRF 3.15 | `TestCase` + `APIClient` |
| Règles métier | services Python (`lmd.py`, `progression.py`, `publication.py`) | tests unitaires |
| Chat/IA | `chat_tuteur`, `quiz_tuteur`, `rag`, `difficulte` | tests avec LLM simulé (`mock`) |
| Frontend | Angular 18 (standalone) | Jasmine/Karma + Chromium headless |
| PWA/hors-ligne | service worker + intercepteur | specs Jasmine |
| Déploiement | cPanel (Passenger, FTP, cron) | vérifications manuelles documentées |

## 1.3 Types de tests retenus

| Type | Périmètre | Outil | Exécuté |
|---|---|---|---|
| Unitaires | LMD, progression, publication, mentions, validations | Django `TestCase` | ✅ |
| Intégration API | auth, RBAC, cours, progression, quiz, chat, stats | `APIClient` | ✅ |
| Sécurité | 401/403, isolation, injection, secrets | tests + script curl | ✅ |
| Frontend | chat, notifications, cache hors-ligne, Markdown | Karma/Jasmine | ✅ (suite critique) |
| Performance | endpoints de lecture | script Python `requests` | ✅ (local) |
| E2E navigateur | parcours complets UI | Playwright/Selenium | ❌ non exécuté |
| IA réelle | qualité des réponses | fournisseur cloud | ❌ non exécuté (pas de clé) |

## 1.4 Outils et justification

- **Django TestCase / DRF APIClient** : outils natifs du projet, base SQLite
  isolée et détruite après chaque exécution.
- **coverage.py** : mesure réelle de la couverture, sans dépendance externe.
- **Karma + Jasmine + Chromium headless** : déjà configurés par Angular ;
  Chromium installé dans le conteneur pour exécuter les specs.
- **script `perf_api.py` (requests)** : pas de JMeter/k6 disponible ; script
  reproductible, mesures réelles, sans revendication de charge production.
- **Script `security_checks.sh`** : contrôles HTTP reproductibles.

## 1.5 Environnements

- **Backend** : conteneur Docker `somapro-backend` (Python 3.12), base de test
  SQLite en mémoire, migrations appliquées automatiquement par Django.
- **Frontend** : conteneur Node 20 (Debian 12), Chromium 156 headless.
- **Charge** : serveur de développement Django (`runserver`), SQLite, local.
- **Aucune donnée de production** n'est utilisée : comptes fictifs
  (`@metier.t`, `chat.test@example.com`).

## 1.6 Risques couverts

- Élévation de privilèges (rôle, IDOR, accès inter-apprenants).
- Contournement du déblocage des blocs.
- Fuite de corrigés / d'évaluations.
- Fuite de secrets IA dans le frontend.
- Injection de prompt (refus déterministe des solutions d'évaluation).
- Erreurs du fournisseur IA (502 contrôlé, pas de panne générale).
- Régression sur les parcours critiques.

## 1.7 Limites assumées

| Limite | Impact | Atténuation |
|---|---|---|
| Pas de tests E2E navigateur | parcours UI non validés de bout en bout | tests API + specs Angular ; à compléter avec Playwright |
| IA en production en mode `mock` | qualité réelle non mesurée | pipeline testé avec LLM simulé ; grille qualité fournie |
| Modèle local 0,5b limité | réponses parfois hors sujet | fournisseur cloud recommandé |
| Charge sur serveur de dev/SQLite | chiffres non transposables à la production | mesure de référence + analyse du goulot |
| 13 specs frontend historiques cassées | compilation globale Karma impossible | `tsconfig.spec.critical.json` dédié ; dette documentée |
