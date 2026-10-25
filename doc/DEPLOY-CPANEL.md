# Déploiement LWS **cPanel** (mutualisé Python) — SOMAPRO

> cPanel ≠ Docker. On utilise **Passenger** (Python), **MySQL/PostgreSQL**, et un **cron**
> à la place de Celery. Les WebSockets ne sont **pas** disponibles (fallback polling).

## 0. Prérequis
- Offre **LWS cPanel** avec **Python 3.11/3.12**, **SSH**, **MySQL** (ou PostgreSQL).
- Deux sous-domaines : `somapro.gconnectapp.com` (site) et `somaproapi.gconnectapp.com` (API).
- Accès cPanel + FTP/SSH.

---

## 1. Base de données (cPanel → MySQL Databases)
1. Créer une base `CPUSER_somapro` + un utilisateur + mot de passe.
2. Noter : `MYSQL_DB`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_HOST` (`localhost`).

> PostgreSQL est aussi supporté (`DB_ENGINE=postgres` + `POSTGRES_*`) si l'offre le fournit.

## 2. Application Python (cPanel → Setup Python App)
| Champ | Valeur |
|---|---|
| Python version | 3.12 |
| Application root | `somapro/backend-api-master2` |
| Application URL | `somaproapi.gconnectapp.com` |
| Application startup file | **`passenger_wsgi.py`** |
| Passenger log file | `somapro/backend-api-master2/passenger.log` |

Créer le virtualenv : cPanel indique le chemin (ex. `~/virtualenv/somaproapi/3.12`).

## 3. Code + configuration
```bash
cd ~/somapro
git clone https://github.com/Fabeci/backend-api-master2.git
cd backend-api-master2
cp deploy/.env.prod.example .env      # puis éditer
```
`.env` minimal :
```dotenv
DJANGO_SECRET_KEY=64-caracteres-aleatoires
DEBUG=False
ALLOWED_HOSTS=somaproapi.gconnectapp.com
CORS_ALLOWED_ORIGINS=https://somapro.gconnectapp.com
CSRF_TRUSTED_ORIGINS=https://somapro.gconnectapp.com,https://somaproapi.gconnectapp.com
DB_ENGINE=mysql
MYSQL_DB=CPUSER_somapro
MYSQL_USER=CPUSER_somapro
MYSQL_PASSWORD=...
MYSQL_HOST=localhost
DEFAULT_INSTITUTION_ID=27
```

## 4. Installation + migrations
```bash
source ~/virtualenv/somaproapi/3.12/bin/activate
pip install -r requirements.docker.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput
mkdir -p tmp && touch tmp/restart.txt
```

## 5. Fichiers statiques & médias
Dans le **docroot** de `somaproapi.gconnectapp.com` (souvent `backend-api-master2/public`),
créer un `.htaccess` :
```apache
Alias /static/ /home/CPUSER/somapro/backend-api-master2/staticfiles/
Alias /media/  /home/CPUSER/somapro/backend-api-master2/media/
```
> Si `Alias` est interdit, copier `staticfiles/` et `media/` dans le docroot.

## 6. Cron (remplace Celery Beat)
cPanel → **Cron Jobs** → ajouter :
```cron
*/5 * * * * /bin/bash /home/CPUSER/somapro/backend-api-master2/deploy/cpanel/cron_publication.sh
```
→ publie les contenus programmés + envoie les rappels de séances.

## 7. Frontend (Angular)
1. `npm run build -- --configuration production`
2. Envoyer `dist/tagus/browser/` dans le docroot de `somapro.gconnectapp.com`.
3. `.htaccess` (SPA) :
```apache
RewriteEngine On
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule ^ index.html [L]
```

## 8. CI/CD GitHub Actions
Workflow : `.github/workflows/deploy-cpanel.yml` (backend).

**Secrets à créer** (Settings → Secrets → Actions, dépôt **backend**) :

| Secret | Valeur |
|---|---|
| `FTP_SERVER` | hôte FTP cPanel |
| `FTP_USERNAME` | utilisateur FTP |
| `FTP_PASSWORD` | mot de passe FTP |
| `FTP_SERVER_DIR` | `/public_html/somapro/` (docroot du site) |
| `CPANEL_HOST` | hôte SSH cPanel |
| `CPANEL_USER` | utilisateur cPanel |
| `CPANEL_SSH_KEY` | clé privée SSH |
| `CPANEL_PORT` | port SSH (optionnel) |

À chaque push sur `main` :
- **frontend** : build → **upload FTP** ;
- **backend** : **SSH** → `deploy/cpanel/deploy-backend.sh`
  (git pull, pip, migrate, collectstatic, restart Passenger, check).

> Sans SSH : utiliser **cPanel → Git Version Control** (pull) + `.cpanel.yml`
> (présent à la racine du dépôt) puis « Deploy HEAD Commit ».

## 9. SSL
cPanel → **SSL/TLS Status** → exécuter **AutoSSL** pour les deux sous-domaines.

## 10. Limites cPanel (à connaître)
| Élément | Impact |
|---|---|
| **WebSockets** (notifications temps réel) | ❌ Passenger/WSGI → le frontend doit **polling** |
| **Celery worker/beat** | ❌ remplacé par **cron 5 min** |
| **Redis** | ❌ (cache mémoire Django ou MySQL) |
| **Docker** | ❌ |
| **Taille des uploads** | limitée par cPanel (`upload_max_filesize`, `post_max_size`) |

## 11. Checklist
- [ ] `DEBUG=False`, `SECRET_KEY` fort
- [ ] `DB_ENGINE=mysql` + base créée + `migrate` OK
- [ ] `passenger_wsgi.py` sélectionné dans Setup Python App
- [ ] `tmp/restart.txt` touché après chaque déploiement
- [ ] `collectstatic` + `Alias /static/` OK
- [ ] Cron 5 min actif
- [ ] FTP frontend → `index.html` présent
- [ ] AutoSSL actif (2 sous-domaines)
- [ ] `https://somaproapi.../api/v1/` → **401** (normal), site → **200**
