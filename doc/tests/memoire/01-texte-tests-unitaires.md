# Texte prêt à coller — « Tests unitaires des règles métier »

> Style académique (nous). Les chiffres sont ceux réellement mesurés.
> Remplacer « Chapitre X » et les numéros de figures/tableaux selon votre plan.

---

## X.3 Tests unitaires des règles métier

### X.3.1 Objectif et périmètre

Les tests unitaires visent les **règles métier** dont une erreur aurait un
impact direct sur la scolarité : calcul des moyennes LMD, déblocage des
contenus, validation des blocs, autorisations, suivi des évaluations.

Douze domaines ont été priorisés selon une approche par les risques :

| Domaine | Risque couvert |
|---|---|
| États d'un cours | statut erroné (planifié/en cours/terminé/annulé) |
| Publication progressive | contenu visible trop tôt ou bloqué à tort |
| Consultation et validation d'un bloc | validation sans activité réelle |
| Déblocage du bloc suivant | accès anticipé au contenu |
| Calculs LMD | moyenne, crédits, mention, semestre erronés |
| Évaluations | note hors barème, pourcentage, accessibilité |
| Validation des questions/réponses | incohérence type/correction |
| RBAC | élévation de privilèges |
| Indicateurs pédagogiques | valeurs aberrantes |
| Suivi des évaluations | soumission après la date limite |
| Progression (cascade) | séquence/module/cours non synchronisés |
| Publication (filtres) | fuite de brouillons |

### X.3.2 Méthode

Chaque scénario est isolé dans une base de test SQLite, recréée et détruite à
chaque exécution. Les assertions portent sur les **effets observables** :
valeur calculée, état enregistré, crédit acquis, verrou levé, exception levée.

Les cas couverts sont systématiquement :
- **nominal** : le comportement attendu dans les conditions normales ;
- **entrées invalides** : champs absents, types incohérents ;
- **valeurs limites** : seuils exacts (10/20, 359/360 s, 79/80 %, 9,99/10) ;
- **erreurs** : exceptions attendues, refus d'accès ;
- **états incohérents** : question sans parent, double bonne réponse, etc.

*Exemple de test de valeur limite (seuil de consultation de 60 % pour un bloc
de 10 minutes) :*

```python
def test_consultation_temps_seuil(self):
    summ = BlocAnalyticsSummary(apprenant=self.apprenant, bloc=self.b1,
                                duree_totale_sec=359)
    self.assertFalse(bloc_est_valide(self.b1, None, summ))
    summ.duree_totale_sec = 360          # 60 % de 10 min
    self.assertTrue(bloc_est_valide(self.b1, None, summ))
```

### X.3.3 Résultats

| Indicateur | Valeur |
|---|---|
| Tests unitaires (règles métier) | **50** |
| Tests unitaires réussis | **50 / 50** |
| Durée d'exécution | **3,3 s** |
| Suite backend complète | **160 / 160** en **58 s** |
| Tests frontend | **33 / 33** |
| **Total automatisé** | **193 tests** |

### X.3.4 Couverture

La couverture globale du code applicatif atteint **40 %**. Ce chiffre doit être
interprété avec prudence : il inclut l'ensemble des modules (dashboards
analytiques, serializers, commandes), dont certains ne sont pas encore testés.

La couverture des **modules porteurs de règles critiques** est nettement plus
élevée :

| Module | Couverture |
|---|---|
| Moteur LMD | **98 %** |
| Progression | **94 %** |
| Tableau de bord tuteur | **93 %** |
| Détection de difficulté | **92 %** |
| Explication d'erreur | **88 %** |
| Modèles analytics | **85 %** |
| Chat (vues) | **85 %** |
| RBAC | **81 %** |
| Moteur de parcours | **80 %** |
| Chat (service) | **78 %** |
| Quiz tuteur | **75 %** |
| Publication | **69 %** |

*(Voir figure « Couverture des modules critiques ».)*

### X.3.5 Anomalies détectées et corrigées

Six anomalies ont été identifiées lors de la mise en place de la démarche :

1. scripts manuels confondus avec des tests (2 erreurs de découverte) ;
2. CI exécutant seulement 26 des 127 tests ;
3. 13 specs frontend historiquement cassées ;
4. une assertion asynchrone incorrecte dans un spec du chat ;
5. options de test dupliquées dans la configuration Angular ;
6. absence de lanceur Chromium compatible avec un conteneur root.

Toutes ont été corrigées sans modifier les règles métier.

### X.3.6 Limites

- Les **moteurs analytiques** (dashboards, compétences) restent peu couverts.
- Les **serializers** ne sont pas exhaustivement testés.
- Les tests unitaires ne remplacent pas les tests d'intégration, de sécurité,
  E2E et de performance, traités dans les sections suivantes.

---

## Transition

Les tests unitaires valident les règles isolées. La section suivante vérifie
leur **intégration** dans les endpoints, les **autorisations** réelles et le
comportement du **chat pédagogique**.
