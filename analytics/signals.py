# analytics/signals.py
# ============================================================================
# SIGNALS — Détection automatique des triggers de difficulté
# Se déclenche après mise à jour des analytics-summary
# ============================================================================

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_seuils(trigger: str) -> dict:
    """Retourne les seuils configurés pour un trigger."""
    return getattr(settings, 'AI_TRIGGERS', {}).get(trigger, {})


def _should_trigger(apprenant, trigger: str, **context) -> bool:
    """Détermine si un trigger doit être activé."""
    from .models import AIAnalysisRequest
    from django.utils import timezone
    from datetime import timedelta

    seuils = _get_seuils(trigger)
    if not seuils:
        return False

    if trigger == 'temps_long':
        ratio = context.get('ratio_temps_pct', 0) / 100
        duree = context.get('duree_totale_sec', 0)
        return (ratio >= seuils.get('ratio_temps_min', 1.5) and
                duree >= seuils.get('min_duree_sec', 300))

    elif trigger == 'multi_reouverture':
        ouvertures = context.get('nb_ouvertures', 0)
        ratio = context.get('ratio_temps_pct', 0) / 100
        return (ouvertures >= seuils.get('max_ouvertures', 3) or
                ratio >= seuils.get('ratio_temps_min', 1.2))

    elif trigger == 'sequence_complexe':
        ratio = context.get('ratio_temps_pct', 0) / 100
        scroll = context.get('scroll_max_pct', 0)
        return (ratio >= seuils.get('ratio_temps_min', 1.4) or
                scroll < seuils.get('scroll_max_pct', 50))

    elif trigger == 'module_difficile':
        score = context.get('score_moyen', 0)
        ratio = context.get('ratio_temps_pct', 0) / 100
        return (score > 0 and score <= seuils.get('score_moyen_max', 45)) or (
                ratio >= seuils.get('ratio_temps_min', 1.3))

    elif trigger == 'quiz_rate':
        score = context.get('score', 0)
        tentatives = context.get('nb_tentatives', 0)
        return (score > 0 and score <= seuils.get('score_max', 50) and
                tentatives >= seuils.get('tentatives_min', 2))

    cutoff = timezone.now() - timedelta(hours=2)
    doublon = AIAnalysisRequest.objects.filter(
        apprenant=apprenant, trigger=trigger,
        status__in=['pending', 'success'],
        created_at__gte=cutoff,
    )
    for key in ('bloc_id', 'sequence_id', 'module_id', 'quiz_id'):
        if key in context:
            doublon = doublon.filter(**{key: context[key]})
    return not doublon.exists()


def _creer_requete_ia(apprenant, trigger: str, **extra):
    """Crée une AIAnalysisRequest et lance le traitement."""
    from .models import AIAnalysisRequest
    import threading

    ai_req = AIAnalysisRequest.objects.create(
        apprenant=apprenant,
        trigger=trigger,
        prompt_context=extra.get('prompt_context', {}),
        ** {k: v for k, v in extra.items()
            if k in ('bloc', 'sequence', 'module', 'cours', 'quiz')}
    )

    def _worker():
        try:
            from .services.ai_claude_service import traiter_demande_ai
            traiter_demande_ai(ai_req)
            # Créer le contenu après succès
            from .views import _creer_contenu_genere
            _creer_contenu_genere(ai_req)
        except Exception as e:
            logger.error('[signals] Erreur IA : %s', e)

    threading.Thread(target=_worker, daemon=True).start()
    logger.info('[signals] Trigger %s détecté → request %s', trigger, ai_req.pk)


# ══════════════════════════════════════════════════════════════════════════════════════
# SIGNAL : BlocAnalyticsSummary mis à jour
# ══════════════════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender='analytics.BlocAnalyticsSummary')
def on_bloc_summary_saved(sender, instance, **kwargs):
    """Détecte les triggers liés à un bloc après mise à jour du résumé."""
    if not instance.apprenant:
        return

    # Trigger : temps_long (ratio > seuil)
    ctx = {
        'ratio_temps_pct': instance.ratio_temps_pct or 0,
        'duree_totale_sec': instance.duree_totale_sec or 0,
        'nb_ouvertures': instance.nb_ouvertures or 0,
        'scroll_max_pct': instance.scroll_max_pct or 0,
        'bloc_id': instance.bloc_id,
        'bloc': instance.bloc,
        'sequence': instance.sequence,
        'module': instance.module,
        'cours': instance.cours,
    }
    if _should_trigger(instance.apprenant, 'temps_long', **ctx):
        _creer_requete_ia(instance.apprenant, 'temps_long', **ctx)

    # Trigger : multi_reouverture
    if _should_trigger(instance.apprenant, 'multi_reouverture', **ctx):
        _creer_requete_ia(instance.apprenant, 'multi_reouverture', **ctx)


# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL : SequenceAnalyticsSummary mis à jour
# ══════════════════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender='analytics.SequenceAnalyticsSummary')
def on_sequence_summary_saved(sender, instance, **kwargs):
    """Détecte les triggers liés à une séquence."""
    if not instance.apprenant:
        return

    ctx = {
        'ratio_temps_pct': instance.ratio_temps_pct or 0,
        'score_moyen': instance.score_moyen_quiz or 0,
        'sequence_id': instance.sequence_id,
        'sequence': instance.sequence,
        'module': instance.module,
        'cours': instance.cours,
    }
    if _should_trigger(instance.apprenant, 'sequence_complexe', **ctx):
        _creer_requete_ia(instance.apprenant, 'sequence_complexe', **ctx)


# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL : ModuleAnalyticsSummary mis à jour
# ══════════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender='analytics.ModuleAnalyticsSummary')
def on_module_summary_saved(sender, instance, **kwargs):
    """Détecte les triggers liés à un module."""
    if not instance.apprenant:
        return

    ctx = {
        'ratio_temps_pct': instance.ratio_temps_pct or 0,
        'score_moyen': instance.score_moyen_quiz or 0,
        'module_id': instance.module_id,
        'module': instance.module,
        'cours': instance.cours,
    }
    if _should_trigger(instance.apprenant, 'module_difficile', **ctx):
        _creer_requete_ia(instance.apprenant, 'module_difficile', **ctx)


# ══════════════════════════════════════════════════════════════════════════════════════
# SIGNAL : Quiz échoué (ProgressionQuiz)
# ══════════════════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender='progress.ProgressionQuiz')
def on_quiz_progress_saved(sender, instance, **kwargs):
    """Détecte les quiz ratés pour trigger quiz_rate."""
    if not hasattr(instance, 'apprenant') or not instance.apprenant:
        return

    score = instance.pourcentage_reussite or 0
    tentatives = instance.numero_tentative or 1
    quiz = getattr(instance, 'quiz', None)

    ctx = {
        'score': score,
        'nb_tentatives': tentatives,
        'quiz_id': getattr(quiz, 'pk', None) if quiz else None,
        'quiz': quiz,
        'sequence': getattr(quiz, 'sequence', None) if quiz else None,
        'module': getattr(getattr(quiz, 'sequence', None), 'module', None) if quiz else None,
        'cours': getattr(getattr(getattr(quiz, 'sequence', None), 'module', None), 'cours', None) if quiz else None,
    }
    if _should_trigger(instance.apprenant, 'quiz_rate', **ctx):
        _creer_requete_ia(instance.apprenant, 'quiz_rate', **ctx)