import logging
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(name='generer_contenu_alternatif', bind=False)
def generer_contenu_alternatif(apprenant_id, bloc_id):
    from users.models import Apprenant
    from courses.models import BlocContenu
    from analytics.models import RecommandationPedagogique

    if settings.USE_AI_MOCK:
        from analytics.services.ai_content_generator_mock import AIContentGeneratorMock
        generator = AIContentGeneratorMock()
    else:
        from analytics.services.ai_content_generator import AIContentGenerator
        generator = AIContentGenerator()

    try:
        apprenant = Apprenant.objects.get(id=apprenant_id)
        bloc = BlocContenu.objects.get(id=bloc_id)

        contenu = generator.generer_approche_alternative(apprenant, bloc)

        if contenu:
            RecommandationPedagogique.objects.create(
                apprenant=apprenant,
                type_recommandation='contenu_alternatif',
                message=f"Un nouveau contenu est disponible pour '{bloc.titre}' !",
                bloc_cible=bloc,
                contenu_genere=contenu,
                priorite=2,
            )
            logger.info("Contenu alternatif genere pour apprenant=%s bloc=%s", apprenant_id, bloc_id)
            return f"Contenu genere pour {apprenant.nom}"
        else:
            logger.warning("Generateur a retourne None pour apprenant=%s bloc=%s", apprenant_id, bloc_id)
            return "Echec de generation (contenu=None)"

    except Exception:
        logger.exception("Erreur dans generer_contenu_alternatif apprenant=%s bloc=%s", apprenant_id, bloc_id)
        raise


@shared_task(name='generer_contenu_remediation', bind=False)
def generer_contenu_remediation(apprenant_id, question_id, bloc_id):
    from users.models import Apprenant
    from evaluations.models import Question
    from courses.models import BlocContenu
    from analytics.models import RecommandationPedagogique

    if settings.USE_AI_MOCK:
        from analytics.services.ai_content_generator_mock import AIContentGeneratorMock
        generator = AIContentGeneratorMock()
    else:
        from analytics.services.ai_content_generator import AIContentGenerator
        generator = AIContentGenerator()

    try:
        apprenant = Apprenant.objects.get(id=apprenant_id)
        question = Question.objects.get(id=question_id)
        bloc = BlocContenu.objects.get(id=bloc_id)

        contenu = generator.generer_remediation(apprenant, question, bloc)

        if contenu:
            RecommandationPedagogique.objects.create(
                apprenant=apprenant,
                type_recommandation='contenu_alternatif',
                message="Un contenu de remediation est pret pour vous aider !",
                bloc_cible=bloc,
                contenu_genere=contenu,
                priorite=1,
            )
            logger.info("Contenu remediation genere pour apprenant=%s question=%s", apprenant_id, question_id)
            return "Contenu de remediation genere"
        else:
            logger.warning("Generateur a retourne None pour remediation apprenant=%s", apprenant_id)
            return "Echec de generation (contenu=None)"

    except Exception:
        logger.exception("Erreur dans generer_contenu_remediation apprenant=%s", apprenant_id)
        raise


@shared_task(name='analyser_progression_quotidienne', bind=False)
def analyser_progression_quotidienne():
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
            except Exception:
                logger.exception("Erreur analyse progression pour apprenant=%s", apprenant.pk)
                continue

        logger.info("Analyse quotidienne : %s recommandations pour %s apprenants", compteur, apprenants.count())
        return f"{compteur} recommandations generees pour {apprenants.count()} apprenants"

    except Exception:
        logger.exception("Erreur globale dans analyser_progression_quotidienne")
        raise
