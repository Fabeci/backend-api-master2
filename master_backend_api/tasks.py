from celery import shared_task
from django.conf import settings
import traceback

@shared_task(name='generer_contenu_alternatif', bind=False)
def generer_contenu_alternatif(apprenant_id, bloc_id):
    """
    Génère un contenu alternatif de manière asynchrone
    """
    print(f"\n{'='*60}")
    print(f"🚀 TÂCHE: generer_contenu_alternatif")
    print(f"   Apprenant ID: {apprenant_id}")
    print(f"   Bloc ID: {bloc_id}")
    print(f"{'='*60}\n")
    
    from users.models import Apprenant
    from courses.models import BlocContenu
    from analytics.models import RecommandationPedagogique
    
    # Choisir le bon générateur
    if settings.USE_AI_MOCK:
        from analytics.services.ai_content_generator_mock import AIContentGeneratorMock
        generator = AIContentGeneratorMock()
        print("📋 Mode MOCK activé")
    else:
        from analytics.services.ai_content_generator import AIContentGenerator
        generator = AIContentGenerator()
        print("🤖 Mode API RÉELLE activé")
    
    try:
        print(f"📥 Récupération de l'apprenant {apprenant_id}...")
        apprenant = Apprenant.objects.get(id=apprenant_id)
        print(f"✅ Apprenant trouvé: {apprenant.nom} {apprenant.prenom}")
        
        print(f"📥 Récupération du bloc {bloc_id}...")
        bloc = BlocContenu.objects.get(id=bloc_id)
        print(f"✅ Bloc trouvé: {bloc.titre}")
        
        print(f"🤖 Appel du générateur d'IA...")
        contenu = generator.generer_approche_alternative(apprenant, bloc)
        
        if contenu:
            print(f"✅ Contenu généré avec ID: {contenu.id}")
            print(f"   Titre: {contenu.titre}")
            print(f"   Longueur HTML: {len(contenu.contenu_html)} caractères")
            
            print(f"📝 Création de la recommandation...")
            reco = RecommandationPedagogique.objects.create(
                apprenant=apprenant,
                type_recommandation='contenu_alternatif',
                message=f"Un nouveau contenu est disponible pour '{bloc.titre}' !",
                bloc_cible=bloc,
                contenu_genere=contenu,
                priorite=2
            )
            print(f"✅ Recommandation créée avec ID: {reco.id}")
            
            return f"✅ Contenu généré pour {apprenant.nom}"
        else:
            print(f"❌ Le générateur a retourné None")
            return f"❌ Échec de génération (contenu=None)"
    
    except Exception as e:
        error_msg = f"❌ ERREUR dans generer_contenu_alternatif: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return error_msg


@shared_task(name='generer_contenu_remediation', bind=False)
def generer_contenu_remediation(apprenant_id, question_id, bloc_id):
    print(f"\n{'='*60}")
    print(f"🚀 TÂCHE: generer_contenu_remediation")
    print(f"   Apprenant ID: {apprenant_id}")
    print(f"   Question ID: {question_id}")
    print(f"   Bloc ID: {bloc_id}")
    print(f"{'='*60}\n")
    
    from users.models import Apprenant
    from evaluations.models import Question
    from courses.models import BlocContenu
    from analytics.models import RecommandationPedagogique
    
    if settings.USE_AI_MOCK:
        from analytics.services.ai_content_generator_mock import AIContentGeneratorMock
        generator = AIContentGeneratorMock()
        print("📋 Mode MOCK activé")
    else:
        from analytics.services.ai_content_generator import AIContentGenerator
        generator = AIContentGenerator()
        print("🤖 Mode API RÉELLE activé")
    
    try:
        print(f"📥 Récupération des données...")
        apprenant = Apprenant.objects.get(id=apprenant_id)
        question = Question.objects.get(id=question_id)
        bloc = BlocContenu.objects.get(id=bloc_id)
        
        print(f"✅ Apprenant: {apprenant.nom}")
        print(f"✅ Question: {question.enonce_texte[:50]}...")
        print(f"✅ Bloc: {bloc.titre}")
        
        print(f"🤖 Appel du générateur d'IA...")
        contenu = generator.generer_remediation(apprenant, question, bloc)
        
        if contenu:
            print(f"✅ Contenu généré avec ID: {contenu.id}")
            print(f"   Titre: {contenu.titre}")
            print(f"   Longueur HTML: {len(contenu.contenu_html)} caractères")
            
            print(f"📝 Création de la recommandation...")
            reco = RecommandationPedagogique.objects.create(
                apprenant=apprenant,
                type_recommandation='contenu_alternatif',
                message=f"Un contenu de remédiation est prêt pour vous aider !",
                bloc_cible=bloc,
                contenu_genere=contenu,
                priorite=1
            )
            print(f"✅ Recommandation créée avec ID: {reco.id}")
            
            return "✅ Contenu de remédiation généré"
        else:
            print(f"❌ Le générateur a retourné None")
            return "❌ Échec de génération (contenu=None)"
    
    except Exception as e:
        error_msg = f"❌ ERREUR dans generer_contenu_remediation: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return error_msg


@shared_task(name='analyser_progression_quotidienne', bind=False)
def analyser_progression_quotidienne():
    """
    Tâche planifiée : analyse tous les apprenants actifs
    """
    from users.models import Apprenant
    from analytics.services.recommendation_engine import RecommendationEngine
    
    try:
        compteur = 0
        apprenants = Apprenant.objects.filter(is_active=True)
        
        for apprenant in apprenants:
            try:
                engine = RecommendationEngine(apprenant)
                recos = engine.analyser_et_recommander()
                compteur += len(recos)
            except Exception as e:
                print(f"Erreur pour {apprenant}: {e}")
                continue
        
        return f"{compteur} recommandations générées pour {apprenants.count()} apprenants"
    
    except Exception as e:
        return f"Erreur globale: {str(e)}"