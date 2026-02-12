import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'master_backend_api.settings')
django.setup()

# Importer l'app Celery
from master_backend_api.celery import app

print("🚀 Lancement du test Celery...")
print(f"📋 Tâches enregistrées : {list(app.tasks.keys())}")

# Appeler la tâche par son nom
result = app.send_task('analyser_progression_quotidienne')
print(f"✅ Tâche lancée : {result.id}")
print(f"📊 Statut initial : {result.status}")

# Attendre le résultat
try:
    resultat = result.get(timeout=30)
    print(f"🎉 Résultat : {resultat}")
except Exception as e:
    print(f"❌ Erreur : {e}")
    import traceback
    traceback.print_exc()