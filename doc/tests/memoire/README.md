# Pack « mémoire & soutenance » — validation logicielle

Ce dossier contient tout ce qui est nécessaire pour intégrer la démarche de
validation dans le mémoire et préparer la soutenance.

| Fichier | Usage |
|---|---|
| `00-plan-chapitre.md` | Plan détaillé du chapitre « Validation et assurance qualité » |
| `01-texte-tests-unitaires.md` | Texte **prêt à coller** (section tests unitaires) |
| `02-tableaux-figures.md` | Tableaux LaTeX + légendes et placement des figures |
| `03-slides-soutenance.md` | Trame de 10 diapositives + notes + démo + questions du jury |
| `04-annexes.md` | Liste des annexes à joindre et consignes de mise en forme |
| `figures/*.svg` | 4 figures générées à partir des chiffres réels |

## Chiffres à utiliser (cohérence)

| Indicateur | Valeur |
|---|---|
| Tests unitaires (règles métier) | **50 / 50** |
| Tests backend (total) | **160 / 160** |
| Tests frontend | **33 / 33** |
| **Total automatisé** | **193** |
| Couverture applicative | **40 %** |
| Couverture modules critiques | **69–98 %** |
| Contrôles de sécurité | **7 / 7** |
| Charge 5 utilisateurs | 32,2 req/s · p95 **297 ms** · 0 erreur |
| Charge 10 utilisateurs | 32,1 req/s · p95 **531 ms** · 0 erreur |
| E2E navigateur | **non exécuté** |
| Qualité IA cloud | **non exécutée** (mode `mock`) |

## Insertion dans Word
1. Copier `01-texte-tests-unitaires.md` (converti en texte) dans le chapitre.
2. Insérer les figures (PNG convertis) avec une légende.
3. Copier les tableaux (ou les recréer avec le style du document).
4. Joindre les annexes (PDF ou impressions des fichiers listés).

## Insertion dans LaTeX
1. Convertir les SVG en PNG/PDF (voir `02-tableaux-figures.md`).
2. Copier les environnements `table`/`figure` fournis.
3. Ajouter les annexes avec `\appendix` et `\chapter{...}`.
4. Vérifier les renvois `\ref{}` (figures, tableaux, annexes).

## Règles de rédaction
- **Ne pas surestimer** : distinguer « testé et réussi » de « non exécuté ».
- **Expliquer le 40 %** : dénominateur large ; les règles critiques sont à 69–98 %.
- **Justifier les choix** : risk-based, outils natifs, reproductibilité.
- **Assumer les limites** : E2E, IA cloud, charge locale.
- **Citer les preuves** : annexes B, C, E, H et identifiants de runs CI.
