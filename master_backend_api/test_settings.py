# master_backend_api/test_settings.py
"""
Réglages pour exécuter la suite de tests SANS Redis ni services externes.

Usage :
    DJANGO_SETTINGS_MODULE=master_backend_api.test_settings \
        python manage.py test ...

Le module réutilise les réglages de production/développement puis remplace
uniquement les briques d'infrastructure par des implémentations en mémoire.
Cela permet de lancer les tests sur un poste sans Docker/Redis, tout en
gardant le même code applicatif et la même base SQLite de test.
"""
from .settings import *  # noqa: F401,F403

# ── Cache / channels : tout en mémoire ──────────────────────────────────────
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'somapro-tests',
    }
}

CHANNEL_LAYERS = {
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
}

# ── Celery : exécution synchrone, sans broker ──────────────────────────────
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# ── Email : boîte mémoire (aucun envoi réel) ───────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
