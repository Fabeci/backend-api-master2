# analytics/services/ai_intervention_service.py
# ============================================================================
# IA CIBLÉE PAR INTERVENTION (Phase 11)
#
# Le MOTEUR décide (« l'apprenant a besoin d'une intervention ») ; l'IA exécute
# (« voici le contenu adapté »). On ne déclenche l'IA que pour une intervention
# de type IA, avec tous les garde-fous :
#   - une seule génération en attente par apprenant (anti-flood)
#   - anti-doublon (contenu/quiz déjà existant pour la cible)
#   - cooldown par intervention
# ============================================================================
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

AI_INTERVENTION_TYPES = {'AI_CONTENT', 'AI_QUIZ'}


def choose_trigger(intervention) -> str:
    """Choisit le trigger IA adapté au type d'intervention."""
    t = intervention.intervention_type
    if t in ('AI_QUIZ', 'RETAKE_QUIZ'):
        return 'quiz_rate'
    if intervention.bloc_id and not intervention.sequence_id:
        return 'multi_reouverture'
    return 'sequence_complexe'   # explication


def build_context(intervention, trigger: str) -> dict:
    """Construit le prompt_context adéquat pour la cible de l'intervention."""
    from ..recommendation_engine import build_sequence_adaptative_context

    if trigger == 'sequence_complexe' and intervention.sequence_id:
        return build_sequence_adaptative_context(intervention.apprenant, intervention.sequence)

    if trigger == 'multi_reouverture' and intervention.bloc_id:
        from .progress_engine import _bloc_duree_estimee_sec
        bloc = intervention.bloc
        seq = getattr(bloc, 'sequence', None)
        mod = getattr(seq, 'module', None) if seq else None
        crs = getattr(mod, 'cours', None) if mod else None
        texte = ''
        import re
        for f in ('contenu_html', 'contenu_texte', 'contenu_markdown', 'code_source'):
            v = getattr(bloc, f, None)
            if v:
                texte = re.sub(r'<[^>]+>', ' ', str(v)).strip()
                break
        return {
            'bloc_titre': getattr(bloc, 'titre', ''),
            'bloc_contenu': texte[:2500],
            'duree_estimee_min': _bloc_duree_estimee_sec(bloc) // 60,
            'duree_passee_min': 0, 'ratio_pct': 0, 'nb_ouvertures': 1, 'scroll_max_pct': 0,
            'cours_titre': crs.titre if crs else '',
            'sequence_titre': seq.titre if seq else '',
        }

    # quiz_rate : on n'a pas forcément de quiz source → contexte minimal + séquence
    seq = intervention.sequence
    crs = intervention.cours
    return {
        'quiz_titre': 'Quiz de consolidation',
        'quiz_description': 'Quiz ciblé sur les notions fragiles.',
        'score_obtenu': 0, 'nb_tentatives': 1, 'questions_ratees': [],
        'cours_titre': crs.titre if crs else '',
        'sequence_titre': seq.titre if seq else '',
    }


def can_generate(intervention) -> tuple:
    """Garde-fous avant génération. Retourne (bool, raison)."""
    from analytics.models import AIAnalysisRequest, ContenuGenere, QuizGenereClaude

    # Anti-flood : une génération à la fois par apprenant.
    # On ignore les `pending` périmés (thread tué) au-delà de 10 min.
    cutoff_pending = timezone.now() - timedelta(minutes=10)
    if AIAnalysisRequest.objects.filter(
        apprenant=intervention.apprenant, status='pending', created_at__gte=cutoff_pending,
    ).exists():
        return False, 'generation_en_cours'

    if intervention.contenu_genere_id or intervention.quiz_genere_id:
        return False, 'deja_genere'

    # Anti-doublon : contenu existant pour la cible
    if intervention.sequence_id and ContenuGenere.objects.filter(
        apprenant=intervention.apprenant, sequence_source_id=intervention.sequence_id,
    ).exists():
        return False, 'contenu_existant'

    # Cooldown : pas de génération pour cette intervention depuis 6 h
    cutoff = timezone.now() - timedelta(hours=6)
    if AIAnalysisRequest.objects.filter(
        intervention=intervention, created_at__gte=cutoff,
    ).exists():
        return False, 'cooldown'

    return True, 'ok'


def request_intervention_generation(intervention):
    """
    Crée (si autorisé) une `AIAnalysisRequest` liée à l'intervention.
    Retourne (request|None, raison).
    """
    from analytics.models import AIAnalysisRequest

    ok, reason = can_generate(intervention)
    if not ok:
        return None, reason

    trigger = choose_trigger(intervention)
    context = build_context(intervention, trigger)

    req = AIAnalysisRequest.objects.create(
        apprenant=intervention.apprenant,
        trigger=trigger,
        prompt_context=context,
        intervention=intervention,
        sequence=intervention.sequence,
        module=intervention.module,
        cours=intervention.cours,
        bloc=intervention.bloc,
    )
    return req, 'created'
