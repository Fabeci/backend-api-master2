# 07 — Tests de sécurité applicative

Date : 31/10/2026  
Périmètre : API Django / DRF + frontend Angular SOMAPRO.  
Environnement : local (SQLite, `master_backend_api.test_settings`) + vérifications HTTP sur l'API live.

## 1. Objectif

Vérifier les attaques classiques contre l'application :

- injection SQL ;
- XSS stocké / réfléchi ;
- IDOR / contrôle d'accès horizontal et vertical ;
- mass assignment / élévation de privilèges ;
- authentification, expiration de token, brute force ;
- upload de fichiers malveillants ;
- CORS et en-têtes de sécurité ;
- dépendances vulnérables.

## 2. Résultats synthétiques

| Catégorie | Résultat |
|---|---|
| Tests d'attaque backend | **19/19 OK** |
| Suite backend complète | **201/201 OK** |
| Build Angular production | **OK** |
| `manage.py check --deploy` avec `DEBUG=False` | **0 avertissement** |
| CORS origine inconnue | **refusée** |
| CORS origine frontend | **autorisée** |
| En-têtes API live | HSTS, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` |

Commande des tests d'attaque :

```bash
python manage.py test core.tests_attaques \
  --settings=master_backend_api.test_settings -v2
```

## 3. Injection SQL

### Vérifications

- payloads `' OR '1'='1`, `' OR 1=1 --` dans le login ;
- payloads dans `search`, `ordering`, `institution`, `q` et les IDs d'URL ;
- payload `Robert'); DROP TABLE academics_departement;--` enregistré comme nom de département.

### Conclusion

**Aucune injection SQL exploitable détectée.**

- Aucun `cursor.execute`, `.raw()`, `.extra()` ou `RawSQL` dans le code applicatif exposé aux requêtes (hors scripts `seed_*.py`).
- Toutes les requêtes passent par l'ORM Django, donc paramétrées.
- Les payloads sont stockés **littéralement** et les tables restent intactes.
- Aucune réponse **500** sur les paramètres malveillants.

## 4. XSS

### Côté API

Un payload `<script>alert(1)</script><img src=x onerror=…>` est renvoyé tel quel en **JSON** (`application/json`). L'API ne rend pas de HTML : le risque se situe côté navigateur.

### Côté frontend — corrections appliquées

| Faille | Correction |
|---|---|
| `dashboard.service.ts` : `exportToPDF()` injectait `title`, clés et valeurs sans échappement dans `document.write()` | ajout de `escapeHtml()` sur toutes les valeurs |
| `course-player` / `tab-modules` : iframes de contenu HTML avec `sandbox="allow-same-origin allow-scripts"` | suppression de `allow-same-origin` ; le script de redimensionnement tourne en origine opaque, sans accès au DOM parent |
| `cours-import-dialog` : aperçu HTML avec `allow-same-origin` | `sandbox=""` |
| URLs `bypassSecurityTrustResourceUrl` (lecteur de cours, PDF, Jitsi) | utilitaire `safeHttpUrl()` : seuls `http(s)`, chemins relatifs et `blob:` sont acceptés ; `javascript:` / `data:text/html` refusés |

### Risque résiduel

Les contenus HTML importés (`docFrameHtml`) utilisent encore un nettoyage par expressions régulières, car le rendu doit conserver les styles inline. La sandbox sans `allow-same-origin` empêche l'accès au parent même si le filtre est contourné. Une évolution vers DOMPurify (avec `style` autorisé) reste recommandée.

## 5. IDOR / contrôle d'accès

Tests réalisés :

- un apprenant ne peut pas lire l'inscription d'un autre apprenant ;
- un apprenant ne peut pas accéder à la classe d'un autre ;
- un admin ne voit pas les départements/filières/classes/inscriptions d'un autre établissement ;
- un admin ne peut pas créer une classe ou une inscription dans un autre établissement ;
- un admin ne peut pas inscrire un apprenant d'un autre établissement.

### Corrections

- `FiliereDetailAPIView` utilisait `get_object_or_404(Filiere, pk=pk)` sans filtrage : remplacé par `get_filtered_academic_object()` + `can_modify_academic_resource()`.
- `ClasseSerializer` / `InscriptionSerializer` : l'établissement du compte est prioritaire ; un payload `institution` différent est refusé.
- `Inscription.clean()` et `InscriptionSerializer.validate()` : l'apprenant doit appartenir à l'établissement de l'inscription.
- Vues `Classe` / `Inscription` : l'institution est forcée côté serveur pour les non-superusers.

## 6. Mass assignment / élévation de privilèges

- `is_superuser`, `is_staff`, `role` restent read-only.
- Les auto-modifications de profil ne peuvent pas modifier :
  - la classe/groupe/tuteur/matricule d'un apprenant ;
  - les groupes/institutions/spécialités d'un formateur ;
  - le département/établissement d'un responsable ;
  - l'établissement d'un parent ou d'un admin.
- Le RBAC refuse déjà ces écritures pour les rôles non habilités ; les protections serializer sont une défense en profondeur.

## 7. Authentification

| Test | Résultat |
|---|---|
| Token invalide | **401** |
| Token expiré | **401** + suppression du token |
| 6e échec de login | **429** |
| Réinitialisation mot de passe, email connu/inconnu | même message, **200** dans les deux cas (pas d'énumération) |

Le cache de verrouillage login utilise désormais un **hash SHA-256** de l'email/IP (évite les clés de cache invalides avec des payloads contenant espaces/quotes).

## 8. Upload

- logo `.php` → **400** ;
- faux `.png` (contenu non image) → **400** ;
- extensions et contenu vérifiés (`PIL.Image.verify()`) ;
- les uploads de blocs de contenu vérifient extension, taille et contenu image.

## 9. CORS et en-têtes

- `Origin: http://evil.example` → **aucun** `Access-Control-Allow-Origin`.
- `Origin: http://localhost:4200` → **autorisé**.
- API live : HSTS, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`.
- `DEBUG=False` : `manage.py check --deploy` → **0 avertissement**.

### Point d'attention

Le site statique `https://somapro.gconnectapp.com/` ne renvoie pas les mêmes en-têtes de sécurité que l'API (HSTS / X-Frame-Options / nosniff / CSP absents). À corriger dans la configuration cPanel/Apache ou le reverse proxy.

## 10. Dépendances

### Backend — `pip-audit -r requirements.txt`

- **93 paquets audités**, **22 paquets vulnérables**, **198 avis**.
- Principaux paquets concernés :

| Paquet | Version | Avis | Correctifs disponibles |
|---|---:|---:|---|
| `pillow` | 11.1.0 | 69 | 12.1.1 → 13.0.0 |
| `django` | 5.1.6 | 31 | 5.1.7 → 5.1.15 |
| `cryptography` | 46.0.4 | 13 | 46.0.5 → 50.0.0 |
| `pyasn1` | 0.6.2 | 12 | 0.6.3 → 0.6.5 |
| `sqlparse` | 0.5.3 | 10 | 0.5.4 / 0.6.0 |
| `twisted` | 25.5.0 | 10 | 26.4.0 |
| `urllib3` | 2.6.3 | 7 | 2.7.0 / 2.8.0 |
| `django-allauth` | 65.4.1 | 6 | 65.13.0 / 65.14.1 |
| `djangorestframework` | 3.15.2 | 5 | 3.17.2 / 3.18.2 |

**Priorité :** Django 5.1.6 → **5.1.15** (correctifs de sécurité dans la même branche), Pillow 11 → **12.1.1+** (surface d'attaque des uploads d'images), puis DRF / allauth / cryptography.

### Frontend — `npm audit --omit=dev`

`npm audit --omit=dev` signale **35 vulnérabilités** :

- **2 critiques** : `@angular/ssr` (SSRF / path traversal Windows), `proxy-addr` ;
- **17 hautes** : `@angular/core`, `@angular/common`, `@angular/compiler`, `@angular/router`, `@angular/service-worker`, `quill`, `prosemirror-view`, `lodash-es`, `postcss`, `tmp`, etc. ;
- **15 modérées**, **1 basse**.

Analyse :

- Le projet utilise **Angular 18.2** (fin de support) ; les correctifs Angular sont publiés en **21.x** (mise à jour majeure).
- Les vulnérabilités `@angular/ssr`, `platform-server`, `express`, `body-parser`, `path-to-regexp` concernent principalement le **SSR / serveur Node**, non utilisé par le SPA déployé.
- Les avis XSS `@angular/core` / `common` / `compiler`, `quill` et `prosemirror-view` sont **pertinents pour le navigateur** et justifient une montée de version planifiée.
- `npm audit fix` ne corrige que les dépendances transitives non majeures ; `--force` casserait la compatibilité Angular.

**Recommandation :** planifier la migration Angular 18 → 21 (ou 20 LTS) avant une mise en production durable, puis relancer `npm audit`, le build et les tests.

## 11. Limites de l'audit

- Pas de test de charge / DDoS.
- Pas de test d'intrusion réseau ou de configuration serveur complète (TLS, WAF, cPanel).
- Les scripts `seed_*.py` (SQL brut) ne sont pas exposés par l'API.
- L'audit des dépendances est un instantané à la date du 31/10/2026.
