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

from .services.quiz_missed import questions_ratees_depuis_passage, questions_ratees  # noqa: E402


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

    elif trigger == 'cours_abandonne':
        ratio = context.get('ratio_completion', 1)
        jours = context.get('jours_inactivite', 0)
        if not (ratio <= seuils.get('ratio_completion_max', 0.3) and
                jours >= seuils.get('jours_inactivite', 14)):
            return False
        # Anti-doublon : une seule tentative par cours et par 24h.
        cutoff = timezone.now() - timedelta(hours=24)
        doublon = AIAnalysisRequest.objects.filter(
            apprenant=apprenant, trigger=trigger,
            status__in=['pending', 'success'],
            created_at__gte=cutoff,
        )
        cours = context.get('cours')
        if cours is not None:
            doublon = doublon.filter(cours=cours)
        return not doublon.exists()

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


def _creer_requete_ia(apprenant, trigger: str, force: bool = False, **extra):
    """Crée une AIAnalysisRequest et lance le traitement (avec anti-flood).

    `force=True` : ignore l'anti-doublon 30 min (l'apprenant demande explicitement
    une NOUVELLE aide pour le même bloc), mais l'anti-flood « une génération à la
    fois » reste appliqué.
    """
    from .models import AIAnalysisRequest
    from django.utils import timezone
    from datetime import timedelta
    import threading

    # ✅ Anti-flood : une seule génération en attente par apprenant (Ollama = 1 slot).
    #    Les `pending` périmés (> 10 min, thread tué) n'bloquent pas.
    if AIAnalysisRequest.objects.filter(
        apprenant=apprenant, status='pending',
        created_at__gte=timezone.now() - timedelta(minutes=10),
    ).exists():
        logger.info('[signals] Requête ignorée (%s) : une génération est déjà en attente', trigger)
        return None

    # ✅ Anti-doublon : même trigger + même cible dans les 30 dernières minutes.
    target = {
        k: v for k, v in extra.items()
        if k in ('bloc', 'sequence', 'module', 'cours', 'quiz') and v is not None
    }
    if not force and target and AIAnalysisRequest.objects.filter(
        apprenant=apprenant, trigger=trigger,
        created_at__gte=timezone.now() - timedelta(minutes=30),
        **target,
    ).exists():
        logger.info('[signals] Requête ignorée (%s) : doublon récent', trigger)
        return None

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
            try:
                ai_req.status = 'error'
                ai_req.error_message = str(e)[:500]
                ai_req.completed_at = timezone.now()
                ai_req.save(update_fields=['status', 'error_message', 'completed_at'])
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()
    logger.info('[signals] Trigger %s détecté → request %s', trigger, ai_req.pk)
    return ai_req


def _bloc_prompt_context(instance) -> dict:
    """Contexte réel d'un bloc (titre + contenu + mesures) pour le prompt IA."""
    from .views import _get_bloc_texte
    bloc = getattr(instance, 'bloc', None)
    est = (getattr(bloc, 'duree_estimee_minutes', 0) or 0) if bloc else 0
    return {
        'bloc_titre':        getattr(bloc, 'titre', '') if bloc else '',
        'bloc_contenu':      _get_bloc_texte(bloc),
        'duree_estimee_min': est,
        'duree_passee_min':  round((instance.duree_totale_sec or 0) / 60, 1),
        'ratio_pct':         instance.ratio_temps_pct or 0,
        'nb_ouvertures':     instance.nb_ouvertures or 0,
        'scroll_max_pct':    instance.scroll_max_pct or 0,
        'cours_titre':       instance.cours.titre if instance.cours else '',
        'sequence_titre':    instance.sequence.titre if instance.sequence else '',
    }


def _sequence_prompt_context(instance) -> dict:
    """Contexte réel d'une séquence (contenu des blocs + lacunes) pour le prompt IA."""
    from .recommendation_engine import build_sequence_adaptative_context
    return build_sequence_adaptative_context(instance.apprenant, instance.sequence)


def _module_prompt_context(instance) -> dict:
    mod = getattr(instance, 'module', None)
    crs = getattr(instance, 'cours', None)
    return {
        'module_titre':      getattr(mod, 'titre', '') if mod else '',
        'module_description': getattr(mod, 'description', '') if mod else '',
        'cours_titre':       getattr(crs, 'titre', '') if crs else '',
        'score_moyen':       instance.score_moyen_quiz or 0,
        'temps_total_min':   round((instance.duree_totale_sec or 0) / 60, 1),
        'ratio_temps_pct':   instance.ratio_temps_pct or 0,
        'concepts_rates':    [],
        'prerequis':         getattr(mod, 'description', '') if mod else '',
    }


def _check_cours_abandonne(apprenant, cours):
    """Évalue l'abandon d'un cours et déclenche la génération d'un parcours de reprise."""
    if apprenant is None or cours is None:
        return
    try:
        from .recommendation_engine import build_cours_abandonne_context
        ctx = build_cours_abandonne_context(apprenant, cours)
        if _should_trigger(apprenant, 'cours_abandonne', cours=cours, **ctx):
            _creer_requete_ia(
                apprenant, 'cours_abandonne',
                prompt_context=ctx,
                cours=cours,
            )
    except Exception as e:  # noqa: BLE001
        logger.error('[signals/cours_abandonne] Erreur: %s', e)


# ══════════════════════════════════════════════════════════════════════════════════════
# SIGNAL : BlocAnalyticsSummary mis à jour
# ══════════════════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender='analytics.BlocAnalyticsSummary')
def on_bloc_summary_saved(sender, instance, **kwargs):
    """
    Triggers liés à un bloc.

    ⚠️ La génération d'aide « temps_long » / « multi_reouverture » n'est plus
    automatique : l'apprenant est d'abord invité à confirmer qu'il est bloqué
    (POST /analytics/blocs/<id>/reponse-aide/). La génération n'a lieu qu'après
    un « oui » (consentement explicite). Rien à faire ici pour l'instant.
    """
    if not instance.apprenant:
        return
    return


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
    if instance.sequence_id and _should_trigger(instance.apprenant, 'sequence_complexe', **ctx):
        # ✅ Ne pas générer de contenu adaptatif pour une séquence déjà validée.
        try:
            from courses.parcours_engine import sequence_est_validee_pour
            if sequence_est_validee_pour(instance.apprenant, instance.sequence):
                pass
            else:
                _creer_requete_ia(instance.apprenant, 'sequence_complexe',
                                  prompt_context=_sequence_prompt_context(instance), **ctx)
        except Exception as e:  # noqa: BLE001
            logger.warning('[signals/sequence_complexe] %s', e)

    # Abandon de cours (progression faible + inactivité prolongée)
    if instance.cours_id:
        _check_cours_abandonne(instance.apprenant, instance.cours)


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
        _creer_requete_ia(instance.apprenant, 'module_difficile',
                          prompt_context=_module_prompt_context(instance), **ctx)


# ══════════════════════════════════════════════════════════════════════════════════════
# SIGNAL : Quiz échoué (ProgressionQuiz)
# ══════════════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# ADAPTIVE — Mastery + Gap après mise à jour SequenceAnalyticsSummary
# ══════════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender='analytics.SequenceAnalyticsSummary')
def on_sequence_summary_saved_mastery(sender, instance, **kwargs):
    """Recalcule mastery → module → cours puis détecte les lacunes."""
    if not instance.apprenant or not instance.sequence_id:
        return
    try:
        from .mastery_engine import (
            compute_sequence_mastery, compute_module_mastery, compute_cours_mastery
        )
        from .gap_engine    import detect_and_update_gap
        from .dropout_engine import check_and_create_alert

        mastery = compute_sequence_mastery(instance.apprenant, instance.sequence)
        if mastery and instance.module:
            compute_module_mastery(instance.apprenant, instance.module)
            if instance.cours:
                compute_cours_mastery(instance.apprenant, instance.cours)
                check_and_create_alert(instance.apprenant, instance.cours)

        detect_and_update_gap(instance.apprenant, instance.sequence)

        # Recalcule le profil adaptatif de l'apprenant
        from .models import LearnerProfile
        profile, _ = LearnerProfile.objects.get_or_create(apprenant=instance.apprenant)
        profile.recalculer()

    except Exception as e:
        logger.error('[signals/mastery] Erreur: %s', e)


# ══════════════════════════════════════════════════════════════════════════════
# PROGRESSION — recalcul de l'état d'apprentissage (Phase 3)
# ══════════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender='courses.BlocProgress')
def on_bloc_progress_saved(sender, instance, **kwargs):
    """Recalcule l'état d'apprentissage quand un bloc est terminé/décoché."""
    if not getattr(instance, 'apprenant_id', None):
        return
    try:
        from .services.progress_engine import refresh_learning_state
        refresh_learning_state(instance.apprenant)
    except Exception as e:  # noqa: BLE001
        logger.error('[signals/learning_state] Erreur: %s', e)


@receiver(post_save, sender='evaluations.PassageQuiz')
def on_passage_quiz_saved(sender, instance, **kwargs):
    """
    Un quiz TERMINÉ met à jour le résumé de séquence (quiz) → ce qui déclenche
    mastery → lacune → recommandation. Indispensable pour que « rater un quiz »
    alimente le moteur.
    """
    if not getattr(instance, 'termine', False) or instance.score is None:
        return
    quiz = getattr(instance, 'quiz', None)
    seq = getattr(quiz, 'sequence', None) if quiz else None
    if seq is None or not getattr(instance, 'apprenant_id', None):
        return
    try:
        # Agrège les quiz d'évaluation ET les quiz du tuteur (« Interroge-moi »).
        from .services.quiz_summary import sync_sequence_quiz_summary

        summ, n, avg = sync_sequence_quiz_summary(instance.apprenant, seq)
        logger.info('[signals/quiz] seq=%s appr=%s quiz moyen=%s%% (%s passages)',
                    seq.pk, instance.apprenant_id, avg, n)

        # ✅ Déclenche la génération d'un QUIZ de remédiation si le score est faible.
        mod = getattr(seq, 'module', None)
        crs = getattr(mod, 'cours', None) if mod else None
        ctx = {
            'score':        float(instance.score or 0),
            'nb_tentatives': n,
            'quiz_id':      getattr(quiz, 'pk', None),
            'quiz':         quiz,
            'sequence':     seq,
            'module':       mod,
            'cours':        crs,
        }
        if _should_trigger(instance.apprenant, 'quiz_rate', **ctx):
            ictx = {
                'quiz_titre':       getattr(quiz, 'titre', '') if quiz else '',
                'quiz_description': getattr(quiz, 'description', '') if quiz else '',
                'score_obtenu':     int(instance.score or 0),
                'nb_tentatives':    n,
                'questions_ratees': questions_ratees_depuis_passage(instance),
                'cours_titre':      crs.titre if crs else '',
                'sequence_titre':   seq.titre,
            }
            _creer_requete_ia(instance.apprenant, 'quiz_rate', prompt_context=ictx, **ctx)
    except Exception as e:  # noqa: BLE001
        logger.error('[signals/quiz_passage] Erreur: %s', e)


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
    seq = ctx.get('sequence')
    crs = ctx.get('cours')
    ictx = {
        'quiz_titre':        getattr(quiz, 'titre', '') if quiz else '',
        'quiz_description':  getattr(quiz, 'description', '') if quiz else '',
        'score_obtenu':      score,
        'nb_tentatives':     tentatives,
        'questions_ratees':  questions_ratees(instance.apprenant, quiz),
        'cours_titre':       crs.titre if crs else '',
        'sequence_titre':    seq.titre if seq else '',
    }
    if _should_trigger(instance.apprenant, 'quiz_rate', **ctx):
        _creer_requete_ia(instance.apprenant, 'quiz_rate', prompt_context=ictx, **ctx)