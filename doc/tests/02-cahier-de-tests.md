# 2. Cahier de tests

Légende : **R** = réussi · **É** = échoué · **B** = bloqué · **NE** = non exécuté.

## 2.1 Backend — règles métier (unitaires) — `core/tests_metier.py` (**50**)

| ID | Fonctionnalité | Préconditions | Résultat attendu | Observé | Statut |
|---|---|---|---|---|---|
| BE-01 | Publication : brouillon/dépublié | Bloc créé | `element_publie` = faux | faux | R |
| BE-02 | Publication : publié | Bloc publié | vrai | vrai | R |
| BE-03 | Publication programmée future | Date + 2 j | faux | faux | R |
| BE-04 | Publication programmée passée | Date - 2 j | vrai | vrai | R |
| BE-05 | Cascade bloc→séquence | Séquence brouillon | `bloc_disponible` = faux | faux | R |
| BE-06 | Bloc masqué | `est_visible=False` | faux | faux | R |
| BE-07 | `filter_disponibles` | 1 visible + 1 brouillon | seul le visible | conforme | R |
| BE-08 | Progression partielle | 1/2 blocs obligatoires | séquence non terminée | non terminée | R |
| BE-09 | Progression complète | 2/2 obligatoires | séquence+module+cours terminés | terminés | R |
| BE-10 | Bloc facultatif | 2 obl. faits, 1 fac. non fait | séquence terminée | terminée | R |
| BE-11 | Mentions LMD | 9,99 / 10 / 12 / 14 / 16 / 18 | Ajourné→Excellent | conforme | R |
| BE-12 | UE validée au seuil | EC à 12/20 | UE validée, 6 crédits | validée, 6 | R |
| BE-13 | UE sous le seuil | 12 et 6 → 9 | non validée, 0 crédit | non validée | R |
| BE-14 | Semestre strict | 1 UE validée + 1 non | semestre invalidé, 6 crédits | invalidé | R |
| BE-15 | Rattrapage meilleure note | 8 normale + 14 rattrapage | 14 | 14 | R |
| BE-16 | Évaluation simple sans sujet | consigne/fichier vides | `ValidationError` | levée | R |
| BE-17 | Accessibilité évaluation | non publiée / future / ouverte | faux / faux / vrai | conforme | R |
| BE-18 | Note > barème / négative | 25 ou -1 sur 20 | `ValidationError` | levée | R |
| BE-19 | Pourcentage | 15/20 | 75 % | 75 | R |
| BE-20 | Parent : enfants autorisés | 1 enfant rattaché + 1 autre | seul l'enfant | conforme | R |
| BE-21 | Apprenant : soi-même | — | lui seul | conforme | R |

## 2.2 Backend — intégration, sécurité, RBAC, IA

| ID | Suite | Nombre | Statut |
|---|---|---|---|
| BE-INT-01 | `core.tests_security` (périmètres, publication, correction, LMD) | 13 | R |
| BE-INT-02 | `core.tests_rbac` (matrice de rôles, périmètres parents/admins) | 13 | R |
| BE-INT-03 | `courses.tests_parcours` (déblocage, reprise, verrou) | 6 | R |
| BE-INT-04 | `courses.tests_p1` (quiz, scores, chevauchements, validation) | 8 | R |
| BE-INT-05 | `courses.tests_chat` (accès, contexte, streaming, quiz, examens, sources, difficulté) | 43 | R |
| BE-INT-06 | `courses.tests_stats` (tableau de bord, périmètre formateur) | 7 | R |
| BE-INT-07 | `evaluations.tests_explication` (« Explique mon erreur ») | 6 | R |
| BE-INT-08 | Autres applications (users, notifications, analytics, etc.) | 20 | R |
| BE-UNIT-09 | Étapes de publication module→séquence→bloc (`tests_metier`) | 4 | R |
| BE-UNIT-10 | États d'un cours (dates, annulé, statut forcé) | 4 | R |
| BE-UNIT-11 | Consultation/validation (seuils 60 %, scroll 80 %) et déblocage du bloc suivant | 6 | R |
| BE-UNIT-12 | Validation des questions/réponses (parent exclusif, types, correction) | 8 | R |
| BE-UNIT-13 | RBAC unitaire (anonyme, superuser, matrice, permission additive, surcharge) | 8 | R |
| BE-UNIT-14 | Indicateurs (profil adaptatif sans activité) et suivi des évaluations | 3 | R |
| **Total** | | **160** | **R** |

## 2.3 Frontend — specs critiques (Jasmine/Karma) — 33

| ID | Fichier | Nombre | Objet | Statut |
|---|---|---|---|---|
| FE-01 | `chat-tuteur.service.spec.ts` | 5 | ouverture, envoi idempotent, nouvelle conversation, suppression, erreur 403 | R |
| FE-02 | `chat-tuteur.component.spec.ts` | 11 | ouverture, streaming, anti-double envoi, erreur, interruption, sources, évaluation bloquée, quiz, nouvelle conversation | R |
| FE-03 | `markdown-lite.pipe.spec.ts` | 7 | gras, listes, code, échappement HTML, titres, null | R |
| FE-04 | `notifications.service.spec.ts` | 6 | polling 30 s, pause onglet, arrêt, absence de WebSocket, compteur, sans jeton | R |
| FE-05 | `offline-cache.interceptor.spec.ts` | 4 | mise en cache, repli hors-ligne, pas de cache POST, purge | R |

> Les **164 specs** du projet contiennent **13 fichiers historiquement cassés**
> (imports de classes inexistantes). Ils sont exclus via
> `tsconfig.spec.critical.json` ; dette documentée (section 3.4).

## 2.4 Sécurité (contrôles dynamiques réels)

| ID | Menace | Attendu | Observé | Statut |
|---|---|---|---|---|
| SEC-01 | Secret IA dans le bundle | absent | 0 occurrence (`sk-ant`, clés, `AI_PROVIDER`) | R |
| SEC-02 | API sans authentification | 401 | 401 | R |
| SEC-03 | Jeton invalide | 401 | 401 | R |
| SEC-04 | Champs sensibles dans le login | absents | pas de `password`/`secret` | R |
| SEC-05 | Apprenant → tableau de bord encadrement | 403 | 403 | R |
| SEC-06 | Message > 2 000 caractères | 400 | 400 | R |
| SEC-07 | Injection de prompt (solution d'examen) | refus | refus explicite déterministe | R |

## 2.5 Performance (réel, local)

| ID | Scénario | Paramètres | Statut |
|---|---|---|---|
| PERF-01 | 5 utilisateurs simultanés | 20 s, 4 endpoints de lecture | R |
| PERF-02 | 10 utilisateurs simultanés | 20 s, mêmes endpoints | R |

## 2.6 Qualité IA — grille d'évaluation

Distinction : **tests automatisés** = LLM simulé (pipeline, sécurité, contexte) ;
**validation qualitative** = fournisseur réel.

| Critère | Pipeline (LLM simulé) | Fournisseur réel local (0,5b) | Cloud |
|---|---|---|---|
| Exactitude | vérifiée par assertions (contenu attendu) | **partielle** (réponses courtes correctes, hors sujet non fiable) | **à réaliser** |
| Pertinence / contexte | le prompt contient le bloc + extraits (testé) | **partielle** | à réaliser |
| Clarté pédagogique | structure du prompt | **correcte** sur réponses courtes | à réaliser |
| Cohérence avec l'historique | historique borné et isolé (testé) | conforme | à réaliser |
| Absence d'affirmations non justifiées | règle dans le prompt + garde déterministe | **non garantie** (a répondu à une question hors sujet) | à réaliser |
| Refus des solutions d'évaluation | garde déterministe | **conforme** | conforme |
| Gestion des erreurs IA | 502 contrôlé (testé) | conforme | à réaliser |

**Conclusion IA** : le pipeline, les garde-fous et l'isolation sont validés ;
la **qualité rédactionnelle réelle nécessite un fournisseur cloud** (clé API),
non disponible en production aujourd'hui (`AI_PROVIDER=mock`).
