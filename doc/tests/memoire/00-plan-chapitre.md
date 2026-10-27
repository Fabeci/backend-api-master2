# Plan du chapitre « Validation et assurance qualité »

> À insérer après le chapitre de réalisation, avant la conclusion générale.
> Durée de lecture visée : 8 à 12 pages + annexes.

## Chapitre X — Validation et assurance qualité

### X.1 Contexte et objectifs
- Pourquoi valider une plateforme LMS (données scolaires, résultats, IA).
- Objectifs : fiabilité, sécurité, non-régression, performance, qualité IA.
- Question de recherche appliquée : *comment garantir la qualité d'un LMS
  multi-rôles intégrant de l'IA sur un hébergement mutualisé ?*

### X.2 Stratégie de validation
- **X.2.1 Approche par les risques** : classer les règles (critiques / importantes / secondaires).
- **X.2.2 Pyramide des tests** : unitaires → intégration → frontend → E2E ; ce qui est exécuté, ce qui ne l'est pas.
- **X.2.3 Outils et environnements** : Django TestCase, DRF APIClient, coverage.py, Jasmine/Karma + Chromium, script de charge, GitHub Actions.
- **X.2.4 Données de test** : comptes fictifs par rôle, cours/modules/séquences/blocs, évaluations, relations parent-enfant ; base SQLite de test détruite après exécution.
- Figure 1 : pyramide des tests.

### X.3 Tests unitaires des règles métier (cœur de l'étape)
- **X.3.1 Périmètre** : 12 domaines (progression, états, publication, déblocage, LMD, évaluations, validations, RBAC, indicateurs…).
- **X.3.2 Méthode** : `TestCase`, `setUp` par scénario, assertions sur les **effets** (états, crédits, verrous), pas seulement l'exécution.
- **X.3.3 Couverture des cas** : nominal, entrées invalides, valeurs limites, erreurs, états incohérents.
- **X.3.4 Résultats** : **50/50** tests unitaires en **3,3 s** ; **160/160** tests backend en **58 s**.
- **X.3.5 Couverture** : **40 %** global applicatif ; **69–98 %** sur les modules critiques.
- **X.3.6 Anomalies détectées et corrigées** (6).
- Figure 2 : couverture par module critique.

### X.4 Tests d'intégration et de sécurité
- 110 tests d'intégration/sécurité/IA (auth, RBAC, cours, progression, quiz, chat, stats, explication).
- 7 contrôles dynamiques (401/403, IDOR, injection de prompt, secrets).
- Tableau : menace → attendu → observé.

### X.5 Tests frontend et non-régression
- 33 specs Jasmine/Karma (chat, notifications, cache hors-ligne, Markdown).
- Configuration Chromium headless, `tsconfig` dédié.
- Dette : 13 specs historiques exclues (documentée).

### X.6 Performance
- Scénarios 5 et 10 utilisateurs, 20 s.
- Résultats : 32 req/s, p95 297→531 ms, 0 erreur.
- Analyse du goulot (runserver/SQLite), recommandations production.
- Figure 3 : latences p50/p95/p99.

### X.7 Analyse statique (SonarQube)
- Instance locale Community, 3 passes (v1.0 → v1.1 → v1.2).
- 236 fichiers, 37 352 lignes ; *quality gate* **Passed**.
- Vulnérabilités **285 → 2** (Docker de dev), blockers **3 → 0**.
- Secret en dur supprimé, PRNG du code de vérification → `secrets`.
- Dette **93,9 h → 78,3 h** ; couverture **39,4 %** (100 % sur le nouveau code).
- Figure 5 : dashboard ; annexe : 2 findings Docker.

### X.8 Intégration continue
- Pipeline GitHub Actions : check → tests → couverture → artefact → déploiement.
- Preuves : runs backend/frontend et déploiements (succès).
- Figure 6 : pipeline.

### X.9 Limites et perspectives
- E2E navigateur non exécuté.
- Validation IA sur fournisseur cloud non réalisée (mode `mock`).
- Charge locale non extrapolable.
- Couverture faible des dashboards analytiques et serializers.
- Perspectives : Playwright, k6 sur préproduction, classificateur de périmètre IA.

### X.10 Conclusion du chapitre
- Ce qui est **prouvé** : 193 tests automatisés, couverture critique, sécurité, analyse statique, CI.
- Ce qui reste **à valider** : E2E, qualité IA cloud, charge production.
- Apport méthodologique : démarche risk-based reproductible sur un LMS.
