# 5. Matrice de traçabilité

| # | Exigence | Règle / attendu | Tests | Statut |
|---|---|---|---|---|
| E1 | Authentification | login valide/invalide, jeton expiré/invalide | `core.tests_security`, `courses.tests_chat`, SEC-02/03/04 | ✅ |
| E2 | Rôles et périmètres | chaque rôle ne voit que son périmètre | `core.tests_rbac`, `courses.tests_stats` | ✅ |
| E3 | Gestion des cours | création/modification réservées au formateur | `core.tests_security` (formateur/module/cours) | ✅ |
| E4 | Publication progressive | brouillon/programmé/publié, dates | `core.tests_security`, `core.tests_metier` (BE-01→07) | ✅ |
| E5 | Progression | bloc terminé → déblocage, cascade | `courses.tests_parcours`, `core.tests_metier` (BE-08→10) | ✅ |
| E6 | Bloc verrouillé | accès refusé côté serveur | `courses.tests_parcours` | ✅ |
| E7 | Quiz / résultats | score, seuils, chevauchement, correction | `courses.tests_p1`, `courses.tests_chat` (quiz) | ✅ |
| E8 | Évaluations | validations de note, accessibilité, pourcentage | `core.tests_metier` (BE-16→19) | ✅ |
| E9 | LMD | moyennes EC→UE→semestre, mentions, rattrapage | `core.tests_metier` (BE-11→15), `core.tests_security` | ✅ |
| E10 | Parent | uniquement ses enfants | `core.tests_rbac`, `core.tests_metier` (BE-20/21) | ✅ |
| E11 | Chat pédagogique | accès apprenant inscrit, contexte, historique isolé | `courses.tests_chat` (43) | ✅ |
| E12 | Anti-triche | assistant suspendu pendant une évaluation | `courses.tests_chat` (423) | ✅ |
| E13 | Quiz IA | génération, secours documentaire, message par type | `courses.tests_chat` (quiz) | ✅ |
| E14 | « Explique mon erreur » | après remise uniquement, propriétaire | `evaluations.tests_explication` | ✅ |
| E15 | Difficulté / remédiation | détection prudente, pas de doublon | `courses.tests_chat` (difficulté) | ✅ |
| E16 | Tableau de bord | agrégats, périmètre formateur, 403 apprenant | `courses.tests_stats` | ✅ |
| E17 | RAG documentaire | indexation PDF, recherche, pas de fuite inter-cours | `courses.tests_chat` (RAG) | ✅ |
| E18 | Notifications | polling 30 s, pause onglet, compteur | `notifications.service.spec.ts` | ✅ |
| E19 | PWA / hors-ligne | cache des cours, repli réseau, purge | `offline-cache.interceptor.spec.ts` | ✅ |
| E20 | Sécurité des données | pas de secret exposé, pas de fuite | `core.tests_security` + SEC-01→07 | ✅ |
| E21 | Erreurs IA | 502 contrôlé, pas de panne | `courses.tests_chat` | ✅ |
| E22 | Non-régression | suite reproductible | 127 tests backend + 33 frontend | ✅ |
| E23 | Performance | latence/débit des endpoints | `perf_api.py` (PERF-01/02) | ✅ (local) |
| E24 | E2E navigateur | parcours UI complets | — | ❌ non exécuté |
| E25 | Qualité IA cloud | exactitude/pertinence rédactionnelle | — | ❌ non exécuté |

## Synthèse

- **23 exigences validées** par exécution réelle.
- **2 exigences non exécutées** (E2E navigateur, qualité IA cloud), avec
  justification et plan de complétion.
- Les règles métier **critiques** (LMD, progression, publication, RBAC, chat,
  évaluation) sont couvertes par des tests automatisés et une couverture
  mesurée de 49 à 98 % selon le module.
