# Tableaux et figures pour le mémoire

## 1. Figures disponibles

| Fichier | Légende proposée | Placement |
|---|---|---|
| `figures/pyramide-tests.svg` | Figure X.1 — Pyramide des tests et volumes exécutés | X.2.2 |
| `figures/couverture-modules.svg` | Figure X.2 — Couverture des modules critiques | X.3.5 |
| `figures/performance-latence.svg` | Figure X.3 — Latence des API selon la charge | X.6 |
| `figures/sonarqube-dashboard.png` | Figure X.4 — *Quality gate* SonarQube après corrections | X.7 |
| `figures/pipeline-ci.svg` | Figure X.5 — Pipeline d'intégration continue | X.8 |

> Annexes possibles : `figures/sonarqube-vulnerabilites.png` (2 findings
> Docker résiduels) et `figures/sonarqube-bugs.png` (6 bugs identifiés).

### Conversion pour Word / LaTeX

```bash
# SVG → PNG (haute résolution) si rsvg-convert est installé
rsvg-convert -z 3 -o couverture.png couverture-modules.svg

# ou via Inkscape
inkscape couverture-modules.svg --export-type=png --export-dpi=300

# ou via Chrome headless
google-chrome --headless --screenshot=couverture.png --window-size=1960,1320 file:///.../couverture-modules.svg
```

- **Word** : Insertion → Images → sélectionner le PNG. Légende : clic droit →
  Insérer une légende.
- **LaTeX** : `\includegraphics[width=\linewidth]{figures/couverture.png}` dans un
  environnement `figure` avec `\caption{}` et `\label{}`.

## 2. Tableaux (LaTeX, booktabs)

### Tableau X.1 — Types de tests, outils et exécution

```latex
\begin{table}[htbp]
\centering
\caption{Types de tests, outils et statut d'exécution}
\label{tab:types-tests}
\begin{tabular}{lllc}
\toprule
Type & Outil & Périmètre & Exécuté \\
\midrule
Unitaires & Django TestCase & règles métier & Oui \\
Intégration & DRF APIClient & API, RBAC, IA simulée & Oui \\
Sécurité & APIClient + script HTTP & 401/403, IDOR, injection & Oui \\
Frontend & Jasmine/Karma + Chromium & chat, notifications, PWA & Oui \\
Performance & script Python (requests) & endpoints de lecture & Oui (local) \\
E2E navigateur & Playwright/Selenium & parcours UI & Non \\
Qualité IA cloud & fournisseur réel & réponses pédagogiques & Non \\
\bottomrule
\end{tabular}
\end{table}
```

### Tableau X.2 — Résultats globaux

```latex
\begin{table}[htbp]
\centering
\caption{Résultats des campagnes de tests}
\begin{tabular}{lrr}
\toprule
Catégorie & Exécutés & Réussis \\
\midrule
Unitaires (règles métier) & 50 & 50 \\
Intégration / sécurité / IA & 110 & 110 \\
Frontend (specs critiques) & 33 & 33 \\
\midrule
\textbf{Total automatisé} & \textbf{193} & \textbf{193} \\
\bottomrule
\end{tabular}
\end{table}
```

### Tableau X.3 — Couverture des modules critiques

```latex
\begin{table}[htbp]
\centering
\caption{Couverture des modules porteurs de règles critiques}
\begin{tabular}{lr}
\toprule
Module & Couverture \\
\midrule
Moteur LMD & 98\,\% \\
Progression & 94\,\% \\
Tableau de bord tuteur & 93\,\% \\
Détection de difficulté & 92\,\% \\
Explication d'erreur & 88\,\% \\
Modèles analytics & 85\,\% \\
Chat (vues) & 85\,\% \\
RBAC & 81\,\% \\
Moteur de parcours & 80\,\% \\
Chat (service) & 78\,\% \\
Quiz tuteur & 75\,\% \\
Publication & 69\,\% \\
\bottomrule
\end{tabular}
\end{table}
```

### Tableau X.4 — Contrôles de sécurité

```latex
\begin{table}[htbp]
\centering
\caption{Contrôles de sécurité et résultats}
\begin{tabular}{lll}
\toprule
Menace & Attendu & Observé \\
\midrule
API sans authentification & 401 & 401 \\
Jeton invalide & 401 & 401 \\
Apprenant $\rightarrow$ dashboard encadrement & 403 & 403 \\
Message $>$ 2\,000 caractères & 400 & 400 \\
Injection de prompt (solution d'examen) & Refus & Refus \\
Secrets IA dans le bundle & Absents & Absents \\
Champs sensibles au login & Absents & Absents \\
\bottomrule
\end{tabular}
\end{table}
```

### Tableau X.5 — Performance (local)

```latex
\begin{table}[htbp]
\centering
\caption{Latence et débit selon la charge (environnement local)}
\begin{tabular}{lrrrrr}
\toprule
Charge & Débit & Moyenne & p95 & p99 & Erreurs \\
\midrule
5 utilisateurs & 32,2 req/s & 155 ms & 297 ms & 366 ms & 0\,\% \\
10 utilisateurs & 32,1 req/s & 310 ms & 531 ms & 637 ms & 0\,\% \\
\bottomrule
\end{tabular}
\end{table}
```

### Tableau X.6 — Analyse statique SonarQube (avant / après)

```latex
\begin{table}[htbp]
\centering
\caption{Analyse statique SonarQube : état initial (v1.0) et final (v1.2)}
\begin{tabular}{lrr}
\toprule
Indicateur & v1.0 (avant) & v1.2 (après) \\
\midrule
Lignes de code analysées (NCLOC) & 41\,548 & 37\,352 \\
Couverture & 36,0\,\% & 39,4\,\% \\
Couverture du nouveau code & -- & 100\,\% \\
Bugs & 6 & 6 \\
Vulnérabilités & 285 & \textbf{2} \\
Code smells & 526 & 430 \\
dont bloquants & 3 & \textbf{0} \\
Duplication & 2,4\,\% & 2,1\,\% \\
Dette technique & 93,9\,h & \textbf{78,3\,h} \\
Fiabilité & C & C \\
Sécurité & E & \textbf{D} \\
Maintenabilité & A & A \\
Quality gate & OK & \textbf{Passed} \\
\bottomrule
\end{tabular}
\end{table}
```

> Commentaire de soutenance : les 2 vulnérabilités restantes concernent
> uniquement le `Dockerfile` de **développement** (COPY récursif, utilisateur
> root) ; la production est déployée sur cPanel sans Docker. Elles sont
> acceptées, justifiées et laissées **visibles** — un finding accepté doit
> rester traçable.

## 3. Conseils de présentation

1. **Ne pas mettre tous les tableaux dans le corps** : garder X.2 (résultats),
   X.3 (couverture) et X.4 (sécurité) ; renvoyer les autres en annexe.
2. **Commenter chaque figure** en une phrase : ce qu'elle montre et ce qu'il
   faut en retenir (pas de paraphrase).
3. **Expliquer le 40 %** : le dénominateur inclut des modules hors périmètre
   (dashboards, serializers) ; la couverture des règles critiques est de 69–98 %.
4. **Distinguer** tests automatisés, tests manuels et éléments non exécutés
   (E2E, IA cloud) — c'est un gage de rigueur, pas une faiblesse.
