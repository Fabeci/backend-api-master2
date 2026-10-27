# 4. Rapport de performance

## 4.1 Configuration

| Élément | Valeur |
|---|---|
| Serveur | Django `runserver` (développement), 1 processus multi-thread |
| Base de données | SQLite (fichier local) |
| Cache | LocMem (pas de Redis) |
| Machine | WSL2 / Docker Desktop, CPU partagé |
| Client | Python `requests`, script `scripts/tests/perf_api.py` |
| Endpoints | `GET /api/v1/cours/`, `/progress/blocs/`, `/annees-scolaires/`, `/notifications/` |
| Compte | apprenant fictif (`chat.test@example.com`) |
| Durée | 20 s par scénario |

> ⚠️ Ces mesures sont une **référence locale**, pas une validation de charge de
> production. La cible cPanel (Passenger/MySQL) doit être mesurée séparément.

## 4.2 Résultats réels

### Scénario PERF-01 — 5 utilisateurs simultanés

| Indicateur | Valeur |
|---|---|
| Requêtes | 650 (650 succès, 0 erreur) |
| Débit | **32,23 req/s** |
| Latence moyenne | **154,75 ms** |
| p50 | 137,85 ms |
| p95 | **297,22 ms** |
| p99 | 365,90 ms |
| Max | 485,88 ms |
| Taux d'erreur | **0 %** |

### Scénario PERF-02 — 10 utilisateurs simultanés

| Indicateur | Valeur |
|---|---|
| Requêtes | 651 (651 succès, 0 erreur) |
| Débit | **32,11 req/s** |
| Latence moyenne | **309,64 ms** |
| p50 | 261,58 ms |
| p95 | **530,89 ms** |
| p99 | 637,03 ms |
| Max | 683,81 ms |
| Taux d'erreur | **0 %** |

Sorties brutes : `raw/perf-concurrency5.json`, `raw/perf-concurrency10.json`.

## 4.3 Analyse

1. **Débit constant (~32 req/s)** entre 5 et 10 utilisateurs → **saturation** du
   serveur de développement (threads) et/ou des accès SQLite.
2. **Latence qui double** (moyenne 155 → 310 ms ; p95 297 → 531 ms) : les
   requêtes s'allongent, mais restent **sans erreur**.
3. **Aucune erreur HTTP** : le comportement est stable, la dégradation est
   progressive (pas d'effondrement).
4. **Goulots probables** :
   - `runserver` (non destiné à la production) ;
   - SQLite (verrous d'écriture, pas de pool) ;
   - requêtes de listes sans cache (pagination DRF par défaut).
5. **Recommandations production** : WSGI/ASGI dédié (Gunicorn/uWSGI/Passenger),
   MySQL/MariaDB, index sur les filtres (`cours`, `apprenant`, `sequence`),
   cache Redis pour les listes, pagination explicite.

## 4.4 Latences IA observées (réelles, local)

| Action | Fournisseur | Durée observée |
|---|---|---|
| Salutation (« bonjour ») | garde locale (sans IA) | **0,25 s** |
| Premier token (streaming) | Ollama 0,5b (CPU) | **< 1 s** |
| Question courte | Ollama 0,5b | **2,6 – 20 s** |
| Génération de quiz (échec de validation) | Ollama 0,5b | **16,8 s** |
| Quiz de secours (contenu) | sans IA | **6,2 s** |
| Génération de quiz | Ollama 1,5b | **87 s** (trop lent) |
| Timeout serveur configuré | — | **75 s** (quiz) |

**Conclusion IA** : la latence dépend fortement du modèle et du CPU. Un
fournisseur cloud (Claude/Gemini) est recommandé pour la production
(objectif 2–5 s).

## 4.5 Limites

- Mesures **locales** (dev server + SQLite), non transposables telles quelles.
- Pas de test JMeter/k6 (indisponibles) ; le script `requests` fournit des
  mesures reproductibles mais moins riches (pas de montée en charge graduelle).
- Pas de monitoring des ressources (CPU/RAM) ; seule la latence côté client
  est mesurée.
- Les endpoints IA n'ont pas été mis sous charge (coût/limites du fournisseur).
