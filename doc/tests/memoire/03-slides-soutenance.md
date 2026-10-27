# Trame de soutenance — validation logicielle

> 10 diapositives, 8 à 10 minutes. Les notes sont le texte à dire.

## Diapositive 1 — Contexte et problématique
- SOMAPRO : LMS multi-rôles (admin, responsable, formateur, apprenant, parent).
- Enjeux : notes LMD, déblocage des contenus, données scolaires, IA pédagogique.
- Problématique : *comment garantir la qualité et la sécurité d'un tel système
  sur un hébergement mutualisé ?*

**Notes** : rappeler que la plateforme est déployée sur cPanel (Passenger,
MySQL/SQLite, cron), sans Docker ni Celery.

## Diapositive 2 — Démarche risk-based
- Classer les règles : critiques (notes, accès, déblocage) / importantes / secondaires.
- Tester d'abord ce qui casse l'école, pas ce qui est facile à tester.
- Pyramide : unitaires → intégration → frontend → E2E.

**Figure** : `pyramide-tests.svg`.

## Diapositive 3 — Tests unitaires : périmètre
- 12 domaines : progression, états, publication, déblocage, LMD, évaluations,
  validations, RBAC, indicateurs, suivi, cascade, filtres.
- Pour chaque règle : nominal, invalide, limites, erreurs, incohérences.
- Exemple : seuil de consultation 359 s → 360 s.

**Notes** : insister sur les assertions d'effets (crédits, verrous), pas sur
l'exécution.

## Diapositive 4 — Résultats des tests
- **50/50** unitaires (3,3 s)
- **160/160** backend (58 s)
- **33/33** frontend
- **193 tests automatisés**

**Figure/tableau** : résultats globaux.

## Diapositive 5 — Couverture
- 40 % global applicatif ; **69–98 %** sur les modules critiques.
- LMD 98 %, progression 94 %, RBAC 81 %, parcours 80 %.
- Le 40 % inclut des modules hors périmètre (dashboards, serializers).

**Figure** : `couverture-modules.svg`.

## Diapositive 6 — Sécurité
- 7 contrôles dynamiques : 401/403, IDOR, injection de prompt, secrets.
- Refus déterministe des solutions d'évaluation (hors modèle).
- Aucun secret IA dans le bundle.

**Tableau** : contrôles de sécurité.

## Diapositive 7 — Performance
- 32 req/s, p95 297 ms (5 utilisateurs), 531 ms (10), **0 erreur**.
- Saturation du serveur de dev/SQLite ; recommandations production
  (WSGI dédié, MySQL, index, cache).

**Figure** : `performance-latence.svg`.

## Diapositive 8 — CI/CD
- GitHub Actions : check → tests → couverture → artefact → déploiement FTP.
- Preuves : 4 workflows verts (CI backend, CI frontend, 2 déploiements).

**Figure** : `pipeline-ci.svg`.

## Diapositive 9 — Limites et transparence
- E2E navigateur non exécuté (outil absent).
- Qualité IA cloud non mesurée (production en mode `mock`).
- Charge locale non extrapolable.
- 13 specs frontend historiques exclues (dette documentée).

## Diapositive 10 — Conclusion
- 193 tests, CI verte, sécurité vérifiée, couverture critique élevée.
- Apport : démarche reproductible et vérifiable, adaptée à un LMS.
- Perspectives : Playwright, k6 sur préproduction, fournisseur IA cloud.

---

## Démonstration (3 minutes, si demandée)
1. Connexion apprenant → ouvrir un cours → valider un bloc → **déblocage du suivant**.
2. Tenter d’ouvrir un bloc verrouillé → **403** (preuve serveur).
3. Ouvrir le chat → poser une question → réponse contextualisée (ou message explicite si IA non configurée).
4. Demander la solution d’un examen → **refus déterministe**.
5. Ouvrir le tableau de bord formateur → agrégats (conversations, notions, refus).
6. Montrer le run GitHub Actions vert (tests + couverture + déploiement).

## Questions probables du jury
- *Pourquoi 40 % de couverture ?* → dénominateur large ; 69–98 % sur les règles
  critiques ; priorisation par le risque.
- *Pourquoi pas d’E2E ?* → outil absent ; tests API + specs frontend ; Playwright
  prévu.
- *L’IA est-elle fiable ?* → pipeline et garde-fous testés ; qualité
  rédactionnelle dépend du modèle ; cloud recommandé.
- *Comment éviter les régressions ?* → CI complète à chaque push + matrice de
  traçabilité.
