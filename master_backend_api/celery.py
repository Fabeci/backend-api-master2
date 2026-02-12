import os
from celery import Celery
from celery.schedules import crontab

# Définir le module Django par défaut
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'master_backend_api.settings')

app = Celery('master_backend_api')

# Charger la config depuis Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-découverte des tâches dans toutes les apps Django
app.autodiscover_tasks()

# ✅ IMPORTANT : Forcer l'import du module tasks
# Ceci doit être APRÈS autodiscover_tasks()
try:
    from . import tasks  # noqa: F401
    print("✅ Module tasks importé avec succès")
except ImportError as e:
    print(f"❌ Erreur import tasks: {e}")

# Tâches planifiées
app.conf.beat_schedule = {
    'analyse-quotidienne': {
        'task': 'analyser_progression_quotidienne',  # ← Utiliser le nom court
        'schedule': crontab(hour=22, minute=0),
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')