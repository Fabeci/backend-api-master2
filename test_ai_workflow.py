import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'master_backend_api.settings')

import django
django.setup()

from django.conf import settings
from users.models import Apprenant
from courses.models import Cours, Module, Sequence, BlocContenu
from evaluations.models import Quiz, Question, Reponse
from analytics.models import BlocAnalytics, QuestionAnalytics, RecommandationPedagogique, ContenuGenere
from master_backend_api.tasks import generer_contenu_alternatif, generer_contenu_remediation, analyser_progression_quotidienne

print("=" * 70)
print("🧪 TEST COMPLET DU SYSTÈME D'IA ADAPTATIVE")
print("=" * 70)

# Vérification de la clé API
print(f"\n🔑 Clé API Anthropic : {'✅ Configurée' if settings.ANTHROPIC_API_KEY else '❌ Manquante'}")
print(f"🤖 Mode Mock : {'✅ Activé' if settings.USE_AI_MOCK else '❌ Désactivé (API réelle)'}")

if not settings.ANTHROPIC_API_KEY and not settings.USE_AI_MOCK:
    print("\n❌ ERREUR : Aucune clé API configurée et mode mock désactivé !")
    exit(1)

# ============================================================================
# ÉTAPE 1 : Préparer les Données de Test
# ============================================================================
print("\n" + "=" * 70)
print("📊 ÉTAPE 1 : PRÉPARATION DES DONNÉES")
print("=" * 70)

# Récupérer un apprenant
apprenant = Apprenant.objects.first()
if not apprenant:
    print("❌ Aucun apprenant trouvé. Veuillez créer un apprenant d'abord.")
    exit(1)

print(f"👤 Apprenant : {apprenant.nom} {apprenant.prenom} (ID: {apprenant.id})")

# Récupérer ou créer un cours
cours = Cours.objects.first()
if not cours:
    print("❌ Aucun cours trouvé. Veuillez créer un cours d'abord.")
    exit(1)

print(f"📚 Cours : {cours.matiere.nom if cours.matiere else 'Sans matière'}")

# Récupérer ou créer un module
module = cours.modules.first()
if not module:
    print("❌ Aucun module trouvé. Créons-en un...")
    module = Module.objects.create(
        cours=cours,
        titre="Module de Test - Python Bases",
        description="Module pour tester l'IA adaptative"
    )
    print(f"✅ Module créé : {module.titre}")
else:
    print(f"📖 Module : {module.titre}")

# Récupérer ou créer une séquence
sequence = module.sequences.first()
if not sequence:
    print("❌ Aucune séquence trouvée. Créons-en une...")
    sequence = Sequence.objects.create(
        module=module,
        titre="Les Variables en Python"
    )
    print(f"✅ Séquence créée : {sequence.titre}")
else:
    print(f"📑 Séquence : {sequence.titre}")

# Récupérer ou créer un bloc
bloc = sequence.blocs_contenu.first()
if not bloc:
    print("❌ Aucun bloc trouvé. Créons-en un...")
    bloc = BlocContenu.objects.create(
        sequence=sequence,
        titre="Introduction aux Variables",
        type_bloc='texte',
        ordre=1,
        contenu_texte="""
        Les variables sont des espaces de stockage en mémoire qui permettent 
        de conserver des valeurs. En Python, on crée une variable simplement 
        en lui assignant une valeur avec le signe =.
        
        Exemple : age = 25
        """,
        duree_estimee_minutes=15,
        est_visible=True
    )
    print(f"✅ Bloc créé : {bloc.titre}")
else:
    print(f"📄 Bloc : {bloc.titre}")

# Créer un quiz avec une question DANS LA MÊME SÉQUENCE
quiz = sequence.quizz.first()
if not quiz:
    print("❌ Aucun quiz trouvé dans cette séquence. Créons-en un...")
    quiz = Quiz.objects.create(
        sequence=sequence,
        titre="Quiz - Variables Python",
        description="Test de compréhension sur les variables"
    )
    print(f"✅ Quiz créé : {quiz.titre}")
else:
    print(f"📝 Quiz : {quiz.titre}")

# ✅ CORRECTION : Vérifier que le quiz a des questions
question = quiz.questions.first()
if not question:
    print("❌ Aucune question dans ce quiz. Créons-en une...")
    question = Question.objects.create(
        quiz=quiz,
        enonce_texte="Quelle syntaxe est correcte pour créer une variable 'nom' contenant 'Alice' ?",
        type_question='choix_unique',
        points=1.0,
        ordre=1
    )
    
    Reponse.objects.create(
        question=question,
        texte="nom = 'Alice'",
        est_correcte=True,
        ordre=1
    )
    Reponse.objects.create(
        question=question,
        texte="var nom = 'Alice'",
        est_correcte=False,
        ordre=2
    )
    Reponse.objects.create(
        question=question,
        texte="String nom = 'Alice'",
        est_correcte=False,
        ordre=3
    )
    
    print(f"✅ Question créée : {question.enonce_texte[:50]}...")
else:
    print(f"❓ Question : {question.enonce_texte[:50]}...")

# ============================================================================
# ÉTAPE 2 : Simuler un Apprenant en Difficulté
# ============================================================================
print("\n" + "=" * 70)
print("⏱️  ÉTAPE 2 : SIMULATION D'UN APPRENANT EN DIFFICULTÉ")
print("=" * 70)

# Simuler un temps excessif passé sur le bloc
analytics, created = BlocAnalytics.objects.get_or_create(
    apprenant=apprenant,
    bloc=bloc,
    defaults={
        'temps_total_secondes': 1200,  # 20 minutes (> 15 min seuil)
        'nombre_visites': 5,
        'pourcentage_scroll': 85
    }
)

if not created:
    analytics.temps_total_secondes = 1200
    analytics.nombre_visites = 5
    analytics.pourcentage_scroll = 85
    analytics.save()

print(f"📊 Analytics créées :")
print(f"   ⏱️  Temps passé : {analytics.temps_total_secondes}s ({analytics.temps_total_secondes // 60} min)")
print(f"   🔄 Visites : {analytics.nombre_visites}")
print(f"   📜 Scroll : {analytics.pourcentage_scroll}%")

# Simuler des échecs sur une question
question_analytics, created = QuestionAnalytics.objects.get_or_create(
    apprenant=apprenant,
    question=question,  # ✅ Maintenant question existe forcément
    defaults={
        'nombre_tentatives': 3,
        'nombre_echecs': 2,
        'temps_moyen_reponse_sec': 45,
        'erreurs_frequentes': [2, 3],
        'concepts_fragiles': ['syntaxe', 'variables']
    }
)

if not created:
    question_analytics.nombre_echecs = 2
    question_analytics.concepts_fragiles = ['syntaxe', 'variables']
    question_analytics.save()

print(f"📝 Question Analytics :")
print(f"   ❌ Échecs : {question_analytics.nombre_echecs}")
print(f"   🎯 Concepts fragiles : {question_analytics.concepts_fragiles}")

# ============================================================================
# ÉTAPE 3 : Tester la Génération de Contenu Alternatif
# ============================================================================
print("\n" + "=" * 70)
print("🤖 ÉTAPE 3 : GÉNÉRATION DE CONTENU ALTERNATIF")
print("=" * 70)

print("🚀 Déclenchement de la tâche asynchrone...")
result = generer_contenu_alternatif.delay(apprenant.id, bloc.id)
print(f"✅ Tâche lancée : {result.id}")
print(f"⏳ En attente du résultat (timeout: 90s)...")

try:
    resultat = result.get(timeout=90)
    print(f"✅ {resultat}")
except Exception as e:
    print(f"❌ Erreur : {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# ÉTAPE 4 : Tester la Génération de Remédiation
# ============================================================================
print("\n" + "=" * 70)
print("🩹 ÉTAPE 4 : GÉNÉRATION DE CONTENU DE REMÉDIATION")
print("=" * 70)

print("🚀 Déclenchement de la tâche asynchrone...")
result = generer_contenu_remediation.delay(apprenant.id, question.id, bloc.id)
print(f"✅ Tâche lancée : {result.id}")
print(f"⏳ En attente du résultat (timeout: 90s)...")

try:
    resultat = result.get(timeout=90)
    print(f"✅ {resultat}")
except Exception as e:
    print(f"❌ Erreur : {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# ÉTAPE 5 : Tester l'Analyse Quotidienne
# ============================================================================
print("\n" + "=" * 70)
print("📊 ÉTAPE 5 : ANALYSE QUOTIDIENNE DE PROGRESSION")
print("=" * 70)

print("🚀 Déclenchement de l'analyse globale...")
result = analyser_progression_quotidienne.delay()
print(f"✅ Tâche lancée : {result.id}")
print(f"⏳ En attente du résultat (timeout: 60s)...")

try:
    resultat = result.get(timeout=60)
    print(f"✅ {resultat}")
except Exception as e:
    print(f"❌ Erreur : {e}")

# ============================================================================
# ÉTAPE 6 : Vérifier les Résultats
# ============================================================================
print("\n" + "=" * 70)
print("📋 ÉTAPE 6 : VÉRIFICATION DES RÉSULTATS")
print("=" * 70)

# Recommandations
recos = RecommandationPedagogique.objects.filter(apprenant=apprenant).order_by('-date_creation')
print(f"\n📌 Recommandations créées : {recos.count()}")
for i, reco in enumerate(recos[:5], 1):
    print(f"   {i}. [{reco.get_type_recommandation_display()}] {reco.message}")
    print(f"      Priorité: {reco.priorite} | Vue: {reco.est_vue} | Suivie: {reco.est_suivie}")

# Contenus générés
contenus = ContenuGenere.objects.filter(apprenant=apprenant).order_by('-date_generation')
print(f"\n📝 Contenus générés : {contenus.count()}")
for i, contenu in enumerate(contenus[:3], 1):
    print(f"\n   {i}. [{contenu.get_type_generation_display()}] {contenu.titre}")
    print(f"      Consulté: {contenu.a_ete_consulte} | Aidé: {contenu.a_aide}")
    print(f"      Concepts: {contenu.concepts_cibles}")
    print(f"\n      📄 Contenu généré par l'IA:")
    print(f"      {'-' * 60}")
    # Afficher un aperçu du contenu HTML
    preview = contenu.contenu_html.replace('<', '\n      <')[:500]
    print(f"      {preview}...")
    print(f"      {'-' * 60}")

# ============================================================================
# RÉSUMÉ FINAL
# ============================================================================
print("\n" + "=" * 70)
print("✨ RÉSUMÉ DU TEST")
print("=" * 70)
print(f"✅ Apprenant testé : {apprenant.nom} {apprenant.prenom}")
print(f"✅ Bloc concerné : {bloc.titre}")
print(f"✅ Question testée : {question.enonce_texte[:50]}...")
print(f"✅ Recommandations générées : {recos.count()}")
print(f"✅ Contenus IA créés : {contenus.count()}")
print("\n🎉 Test terminé avec succès !")
print("=" * 70)