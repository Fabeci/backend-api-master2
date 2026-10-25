import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'master_backend_api.settings')

import django
django.setup()

from users.models import Apprenant
from courses.models import Cours, Module, Sequence, BlocContenu
from analytics.models import BlocAnalytics
from master_backend_api.tasks import generer_contenu_alternatif
from django.utils import timezone

print("🧪 Test du workflow complet")
print("=" * 60)

# 1. Récupérer un apprenant
apprenant = Apprenant.objects.first()
if not apprenant:
    print("❌ Aucun apprenant trouvé. Créez-en un d'abord.")
    exit()

print(f"👤 Apprenant : {apprenant.nom} {apprenant.prenom}")

# 2. Récupérer ou créer un bloc de contenu
bloc = BlocContenu.objects.first()
if not bloc:
    print("❌ Aucun bloc trouvé. Créez-en un d'abord.")
    exit()

print(f"📚 Bloc : {bloc.titre}")

# 3. Simuler un temps excessif sur le bloc
analytics, created = BlocAnalytics.objects.get_or_create(
    apprenant=apprenant,
    bloc=bloc,
    defaults={
        'temps_total_secondes': 1200,  # 20 minutes (> seuil de 15 min)
        'nombre_visites': 5,
        'pourcentage_scroll': 85
    }
)

if not created:
    analytics.temps_total_secondes = 1200
    analytics.nombre_visites = 5
    analytics.save()

print(f"📊 Analytics : {analytics.temps_total_secondes}s sur {analytics.nombre_visites} visites")

# 4. Déclencher la génération de contenu alternatif
print("\n🤖 Déclenchement de la génération IA...")
result = generer_contenu_alternatif.delay(apprenant.id, bloc.id)

print(f"✅ Tâche lancée : {result.id}")
print(f"⏳ En attente du résultat...")

try:
    resultat = result.get(timeout=60)  # Attendre jusqu'à 60 secondes
    print(f"🎉 {resultat}")
except Exception as e:
    print(f"❌ Erreur : {e}")

# 5. Vérifier les recommandations créées
from analytics.models import RecommandationPedagogique
recos = RecommandationPedagogique.objects.filter(apprenant=apprenant)
print(f"\n📌 Recommandations : {recos.count()}")
for reco in recos[:3]:
    print(f"  - {reco.type_recommandation} : {reco.message}")

# 6. Vérifier les contenus générés
from analytics.models import ContenuGenere
contenus = ContenuGenere.objects.filter(apprenant=apprenant)
print(f"\n📝 Contenus générés : {contenus.count()}")
for contenu in contenus[:3]:
    print(f"  - {contenu.titre} ({contenu.type_generation})")