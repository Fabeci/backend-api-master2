# Déploiement & CI/CD — SOMAPRO

## ⚠️ Choisir le bon hébergement LWS (déterminant)

| Offre LWS | Python/Django | Docker | Celery (publication programmée) | Verdict |
|---|---|---|---|---|
| **LWS Panel** (mutualisé) | ❌ PHP/MySQL uniquement | ❌ | ❌ | **Impossible** pour le backend |
| **LWS cPanel** (mutualisé Python) | ✅ via Passenger/WSGI | ❌ | ❌ (remplacer par **cron**) | Possible avec adaptations |
| **LWS VPS** | ✅ | ✅ | ✅ | **Recommandé** |

> Le `Dockerfile`/`docker-compose` de production ci-dessous cible un **VPS LWS**.
> Sur **LWS Panel**, seul le **frontend Angular** (fichiers statiques) peut être hébergé ; le backend doit aller ailleurs.

---

## 1. Architecture de production (VPS)

```
Internet
  │
  ├─ somapro.gconnectapp.com      → Nginx → Angular (dist/tagus/browser)
  └─ somaproapi.gconnectapp.com   → Nginx → Daphne (Django ASGI) → PostgreSQL
                                             ├─ Celery worker   (Redis)
                                             ├─ Celery beat     (publication progressive)
                                             └─ /media /static  (volumes)
```

Fichiers :
- `backend-api-master2/deploy/docker-compose.prod.yml`
- `backend-api-master2/deploy/nginx/somapro.conf`
- `backend-api-master2/deploy/.env.prod.example`
- `master-frontend/Dockerfile.prod`
- `backend-api-master2/deploy/deploy.sh`, `backup.sh`
- `.github/workflows/ci.yml` (dans les 2 dépôts) + `.github/workflows/deploy.yml`

---

## 2. Préparation du serveur (une seule fois)

```bash
# Ubuntu/Debian, en root
apt update && apt install -y git docker.io docker-compose-plugin
mkdir -p /opt/somapro && cd /opt/somapro
git clone https://github.com/Fabeci/backend-api-master2.git
git clone https://github.com/Fabeci/master-frontend.git

# Configuration (jamais commitée)
cd backend-api-master2/deploy
cp .env.prod.example .env.prod
nano .env.prod          # SECRET_KEY, POSTGRES_PASSWORD, EMAIL, etc.
```

### DNS (chez LWS)
| Enregistrement | Valeur |
|---|---|
| `A  somapro` | IP du VPS |
| `A  somaproapi` | IP du VPS |

### SSL (Let's Encrypt — recommandé)
```bash
apt install -y certbot
certbot certonly --standalone -d somapro.gconnectapp.com -d somaproapi.gconnectapp.com
```
Puis dans `deploy/nginx/somapro.conf` :
- ajouter `listen 443 ssl;` + `ssl_certificate /etc/letsencrypt/live/.../fullchain.pem;`
- monter `/etc/letsencrypt` dans le service `frontend`
- rediriger le port 80 vers 443.

---

## 3. Premier déploiement

```bash
cd /opt/somapro
bash backend-api-master2/deploy/deploy.sh
```
Vérifier :
```bash
docker compose -f backend-api-master2/deploy/docker-compose.prod.yml ps
curl -I http://somaproapi.gconnectapp.com/api/v1/     # 401 = normal
curl -I http://somapro.gconnectapp.com/               # 200
```

---

## 4. CI/CD GitHub Actions

### CI (automatique à chaque push)
- **backend** : `manage.py check` + **tests** `core.tests_security` et `core.tests_rbac` (26 tests).
- **frontend** : `npm ci` + **build production**.

### CD (déploiement sur `main`)
`.github/workflows/deploy.yml` se connecte en SSH et lance `deploy.sh`
(pull des 2 dépôts → build Docker → migrations → collectstatic → check).

**Secrets à créer** (Settings → Secrets and variables → Actions) :

| Secret | Valeur |
|---|---|
| `DEPLOY_HOST` | IP ou hostname du VPS |
| `DEPLOY_USER` | utilisateur SSH (ex. `root` ou `deploy`) |
| `DEPLOY_SSH_KEY` | **clé privée** SSH (contenu de `~/.ssh/id_ed25519`) |
| `DEPLOY_PORT` | port SSH (optionnel, défaut 22) |

Génération de la clé (en local) :
```bash
ssh-keygen -t ed25519 -C "github-actions-somapro" -f ~/.ssh/somapro_deploy
ssh-copy-id -i ~/.ssh/somapro_deploy.pub user@IP_DU_VPS
# Copier le CONTENU de ~/.ssh/somapro_deploy (privée) dans DEPLOY_SSH_KEY
```

> Le workflow de déploiement est dans le dépôt **backend** (il orchestre les deux).

---

## 5. Sauvegardes

```bash
bash backend-api-master2/deploy/backup.sh          # db + médias dans backend/backups/
```
Automatisation quotidienne (crontab serveur) :
```cron
0 3 * * * cd /opt/somapro && bash backend-api-master2/deploy/backup.sh >/dev/null 2>&1
```

---

## 6. Alternative LWS cPanel (si pas de VPS)

Sur un **cPanel avec Python** :
1. **Frontend** : `npm run build -- --configuration production` puis envoyer `dist/tagus/browser` en **FTP** (ou `git pull` + build).
2. **Backend** : application Python (Passenger) pointant sur `master_backend_api.wsgi`,
   `pip install -r requirements.docker.txt` dans un virtualenv,
   variables dans `passenger_wsgi.py`/`.env`,
   **base MySQL/PostgreSQL** fournie par cPanel.
3. **Celery** ❌ : remplacer par un **cron** toutes les 5 min :
   ```cron
   */5 * * * * /home/USER/virtualenv/app/3.12/bin/python /home/USER/app/manage.py shell -c "from master_backend_api.tasks import publier_contenus_programmes; publier_contenus_programmes()"
   ```
4. **Fichiers statiques** : `manage.py collectstatic` + règle `.htaccess`.

---

## 7. Checklist avant mise en production

- [ ] `DEBUG=False`
- [ ] `DJANGO_SECRET_KEY` fort (64 caractères)
- [ ] `ALLOWED_HOSTS` = domaines réels
- [ ] `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` = domaines HTTPS
- [ ] PostgreSQL (pas SQLite)
- [ ] HTTPS actif (Let's Encrypt)
- [ ] `docker compose ps` : tous les services **Up**
- [ ] `curl` API → 401 (normal), site → 200
- [ ] **Sauvegarde** testée (restauration incluse)
- [ ] `.env.prod` **hors** du dépôt (déjà ignoré)
